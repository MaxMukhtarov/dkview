import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"

sys.path.insert(0, str(ROOT / "src"))


@pytest.fixture(autouse=True)
def _run_outside_the_project(tmp_path, monkeypatch):
    """Child processes start in a temp folder, not in the project folder,
    which may sit on a network mount where `sh` can fail to read its cwd."""
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def fixture_lines():
    def read(name):
        return (FIXTURES / name).read_text(encoding="utf-8").splitlines()
    return read


@pytest.fixture
def fake_docker(tmp_path):
    """Put a fake `docker` first on PATH; returns a helper to run dkview."""
    if os.name == "nt":
        pytest.skip("the fake docker is a shell script")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(
        f"#!/bin/sh\nexec {sys.executable} {Path(__file__).parent / 'fake_docker.py'} \"$@\"\n"
    )
    docker.chmod(docker.stat().st_mode | stat.S_IEXEC)
    log = tmp_path / "calls.jsonl"

    env = dict(os.environ)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env["PYTHONPATH"] = str(ROOT / "src")
    env["FAKE_DOCKER_LOG"] = str(log)
    env.pop("DKVIEW_OPTS", None)

    class Runner:
        def run(self, *args, timeout=10, **kw):
            return subprocess.run(
                [sys.executable, "-m", "dkview", "--no-color", "--width", "120", *args],
                env={**env, **kw.pop("env", {})}, capture_output=True, text=True,
                timeout=timeout, **kw,
            )

        def calls(self):
            if not log.exists():
                return []
            return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]

    return Runner()
