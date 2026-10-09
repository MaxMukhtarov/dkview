import io
import sys

import pytest

from dkview import ansi, docker, engine
from dkview.features import dashboard, errors, shell


@pytest.mark.parametrize("program, kind", [
    ("docker", "docker"), ("/usr/bin/podman", "podman"), ("docker.exe", "docker"),
    (r"C:\Program Files\Docker\Docker\resources\bin\docker.EXE", "docker"),
    ("podman.exe", "podman"), ("kubectl", ""), ("dockerd", ""),
])
def test_engine_kind(program, kind):
    assert engine.kind(program) == kind


def test_podman_commands_are_understood():
    assert docker.is_docker(["podman", "ps"])
    assert docker.classify(["podman", "ps", "-a"]).name == "table"
    assert docker.classify(["podman", "logs", "web"]).name == "logs"
    assert engine.is_podman(["/usr/bin/podman"])


def test_engine_choice(monkeypatch):
    monkeypatch.setenv("DKVIEW_ENGINE", "podman")
    assert engine.name() == "podman"
    assert docker.expand_shortcut(["ps", "-a"]) == ["podman", "ps", "-a"]
    monkeypatch.delenv("DKVIEW_ENGINE")
    monkeypatch.setattr(engine.shutil, "which", lambda name: name == "podman" and "/usr/bin/podman")
    assert engine.name() == "podman"
    monkeypatch.setattr(engine.shutil, "which", lambda name: "/usr/bin/" + name)
    assert engine.name() == "docker"
    monkeypatch.setattr(engine.shutil, "which", lambda name: None)
    assert engine.name() == "docker"


def test_podman_labels_and_info():
    assert errors._labels({"com.docker.swarm.service.name": "api"}) == {
        "com.docker.swarm.service.name": "api"}
    assert errors._labels(None) == {}
    assert errors._labels("a=1,b=2") == {"a": "1", "b": "2"}
    header = dashboard._header({"host": {"hostname": "vm", "cpus": 4, "memTotal": 2 * 1024 ** 3},
                                "version": {"Version": "4.9.3"}})
    assert ansi.strip(header) == "Podman 4.9.3 on vm · 4 CPUs · 2.0GiB RAM"


def test_powershell_integration():
    script = shell.script("powershell")
    assert "function docker" in script and "IsOutputRedirected" in script
    assert "powershell" in shell.USAGE


def test_output_never_crashes_on_old_code_pages(monkeypatch):
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1252", newline="\n")
    monkeypatch.setattr(sys, "stdout", stream)
    ansi.prepare_output()
    sys.stdout.write("● ✓ ┌─┐ ü 漢\n")
    sys.stdout.flush()
    assert raw.getvalue() == "* OK +-+ ü ?\n".encode("cp1252")


def test_utf8_output_is_left_alone(monkeypatch):
    stream = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
    monkeypatch.setattr(sys, "stdout", stream)
    ansi.prepare_output()
    assert sys.stdout is stream
