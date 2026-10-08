"""The whole tool against a real docker daemon (REAL_DOCKER=1).

Run the same file against each docker version to support, e.g. in the
GitHub Actions matrix (.github/workflows/tests.yml).
"""

import re
import subprocess
import sys
import time

import pytest

from pprint_docker import docker as docker_cli
from pprint_docker import formats
from pprint_docker.features import tables
from pprint_docker.runner import capture
from pprint_docker.table import parse

from .conftest import ROOT

# Values that change between two calls a moment apart.
_MOVING = re.compile(r"\d+(\.\d+)?\s*(%|[kKMGT]i?B|B\b)|\d+ (second|minute)s?|"
                     r"less than a second|about a minute|\d+s\b")


def _steady(table):
    rows = [[_MOVING.sub("~", v) for v in row] for row in table.rows]
    return table.headers, sorted(rows)


JSON_COMMANDS = [
    "ps -a", "ps -s", "container ls -a",
    "images", "images --digests", "image ls",
    "service ls", "service ps rt_api", "service ps rt_broken", "stack ps rt",
    "node ls", "node ps", "stats",
]


@pytest.mark.parametrize("command", JSON_COMMANDS)
def test_json_table_matches_docker_text(host, command):
    """Every JSON field maps to the column docker itself prints."""
    prepared = docker_cli.prepare(["docker"] + command.split(), trunc=False)
    for _ in range(3):  # a task may start or stop between the two calls
        result, json_table = tables.read_json(prepared)
        assert json_table is not None, f"docker {host} rejected the JSON template: " \
            + (result.stderr if result else "fell back to text")
        text = capture(prepared)
        assert text.code == 0, text.stderr
        text_table = parse(text.stdout.splitlines())
        assert text_table is not None
        if _steady(json_table) == _steady(text_table):
            break
        time.sleep(2)
    assert _steady(json_table) == _steady(text_table)


def test_every_layout_is_covered():
    covered = {" ".join(c.split()[:2]) for c in JSON_COMMANDS} | {"ps", "images", "stats"}
    for words in formats.LAYOUTS:
        if words[-1] == "list":
            continue
        assert " ".join(words) in covered or words in {("container", "ps"), ("container", "stats")}


def run(*args, timeout=60):
    return subprocess.run(
        [sys.executable, "-m", "pprint_docker", "--no-color", "--width", "120", *args],
        capture_output=True, text=True, timeout=timeout, cwd=ROOT,
        env={**__import__("os").environ, "PYTHONPATH": str(ROOT / "src")},
    )


CLI = [
    # (arguments, exit codes allowed, text the output must contain)
    (["ps", "-a"], {0}, "rt_web"),
    (["--short", "--sort", "created", "--desc", "ps", "-a"], {0}, "rt_done"),
    (["--cols", "name,status", "ps"], {0}, "NAMES"),
    (["images"], {0}, "busybox"),
    (["images", "--group"], {0}, "busybox"),
    (["service", "ls"], {0}, "rt_api"),
    (["service", "ps", "rt_broken"], {0}, "Failed"),
    (["stack", "ls"], {0}, "rt"),
    (["stack", "services", "rt"], {0}, "rt_worker"),
    (["node", "ls"], {0}, "Leader"),
    (["network", "ls"], {0}, "ingress"),
    (["volume", "ls"], {0}, "DRIVER"),
    (["system", "df"], {0}, "Images"),
    (["stats"], {0}, "CPU %"),
    (["inspect", "rt_web"], {0}, "rt_web"),
    (["--full", "inspect", "rt_web"], {0}, "rt_web"),
    (["service", "inspect", "rt_api"], {0}, "rt_api"),
    (["logs", "rt_web"], {0}, "InvalidOperationException"),
    (["service", "logs", "rt_api"], {0}, "ERROR Timeout"),
    (["dash"], {0}, "rt_web"),
    (["doctor"], {1}, "rt_broken"),
    (["errors"], {1}, "rt_api"),
    (["errors", "rt"], {1}, "ERROR Timeout calling"),
    (["errors", "rt_web", "--since", "1h"], {1}, "InvalidOperationException"),
    (["errors", "rt_worker"], {0}, "none in 1 source"),
    (["clean", "--dry-run"], {0}, ""),
    (["docker", "version"], {0}, "Server"),
]


@pytest.mark.parametrize("args, codes, expected", CLI, ids=lambda v: " ".join(v) if isinstance(v, list) else "")
def test_cli(host, args, codes, expected):
    result = run(*args)
    assert "Traceback" not in result.stderr, result.stderr
    assert result.returncode in codes, result.stdout + result.stderr
    assert expected in result.stdout


def test_errors_groups_repeats(host):
    out = run("errors", "rt_api").stdout
    timeout_rows = [line for line in out.splitlines() if "ERROR Timeout calling" in line]
    assert len(timeout_rows) == 1, out          # one group, not one row per IP/order
    assert "warning" in out.splitlines()[0]


def test_doctor_explains_the_failure(host):
    out = run("doctor").stdout
    assert "✗ rt_broken" in out or "! rt_broken" in out
    assert "exit (3)" in out
