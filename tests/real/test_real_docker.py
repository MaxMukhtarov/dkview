"""The whole tool against a real docker daemon (REAL_DOCKER=1).

Run the same file against each docker version to support, e.g. in the
GitHub Actions matrix (.github/workflows/tests.yml).
"""

import os
import re
import subprocess
import sys
import time

import pytest

from dvt import docker as docker_cli
from dvt import formats
from dvt.features import tables
from dvt.runner import capture
from dvt.table import parse

from .conftest import ENGINE, PODMAN, ROOT

SWARM = pytest.mark.skipif(PODMAN, reason="podman has no swarm")

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
# Podman's own text differs from docker's (headers like "NET IO", extra
# stats columns), so only the commands with the same text are compared.
PODMAN_SAME_TEXT = {"ps -a", "ps -s", "container ls -a", "images", "images --digests", "image ls"}


@pytest.mark.parametrize("command", JSON_COMMANDS)
def test_json_table_matches_docker_text(host, command):
    """Every JSON field maps to the column docker itself prints."""
    if PODMAN and command not in PODMAN_SAME_TEXT:
        pytest.skip("podman: swarm command or different text layout")
    prepared = docker_cli.prepare([ENGINE] + command.split(), trunc=False)
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
        [sys.executable, "-m", "dvt", "--no-color", "--width", "120", *args],
        capture_output=True, text=True, timeout=timeout,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
    )


SW = "swarm"  # needs docker swarm (skipped on podman)
CLI = [
    # (arguments, exit codes allowed, text the output must contain, needs)
    (["ps", "-a"], {0}, "rt_web", ""),
    (["--short", "--sort", "created", "--desc", "ps", "-a"], {0}, "rt_done", ""),
    (["--cols", "name,status", "ps"], {0}, "NAMES", ""),
    (["images"], {0}, "busybox", ""),
    (["images", "--group"], {0}, "busybox", ""),
    (["service", "ls"], {0}, "rt_api", SW),
    (["service", "ps", "rt_broken"], {0}, "Failed", SW),
    (["stack", "ls"], {0}, "rt", SW),
    (["stack", "services", "rt"], {0}, "rt_worker", SW),
    (["node", "ls"], {0}, "Leader", SW),
    (["network", "ls"], {0}, "ingress", SW),
    (["volume", "ls"], {0}, "rt_data", ""),
    (["system", "df"], {0}, "Images", ""),
    (["stats"], {0}, "CPU %", ""),
    (["inspect", "rt_web"], {0}, "rt_web", ""),
    (["--full", "inspect", "rt_web"], {0}, "rt_web", ""),
    (["service", "inspect", "rt_api"], {0}, "rt_api", SW),
    (["logs", "rt_web"], {0}, "InvalidOperationException", ""),
    (["service", "logs", "rt_api"], {0}, "ERROR Timeout", SW),
    (["dash"], {0}, "rt_web", ""),
    (["doctor"], {1}, "rt_broken", SW),
    (["errors"], {1}, "rt_api", SW),
    (["errors"], {1}, "rt_web", ""),
    (["errors", "rt"], {1}, "ERROR Timeout calling", SW),
    (["errors", "rt_web", "--since", "1h"], {1}, "InvalidOperationException", ""),
    (["errors", "rt_worker"], {0}, "none in 1 source", SW),
    (["errors", "rt_done"], {0}, "none in 1 source", ""),
    (["clean", "--dry-run"], {0}, "", ""),
    (["version"], {0}, "Version", ""),
]


@pytest.mark.parametrize("args, codes, expected, needs", CLI,
                         ids=lambda v: " ".join(v) if isinstance(v, list) else "")
def test_cli(host, args, codes, expected, needs):
    if needs == SW and PODMAN:
        pytest.skip("podman has no swarm")
    result = run(*args)
    assert "Traceback" not in result.stderr, result.stderr
    assert result.returncode in codes, result.stdout + result.stderr
    assert expected in result.stdout


@SWARM
def test_errors_groups_repeats(host):
    out = run("errors", "rt_api").stdout
    timeout_rows = [line for line in out.splitlines() if "ERROR Timeout calling" in line]
    assert len(timeout_rows) == 1, out          # one group, not one row per IP/order
    assert "warning" in out.splitlines()[0]


@SWARM
def test_doctor_explains_the_failure(host):
    out = run("doctor").stdout
    assert "✗ rt_broken" in out or "! rt_broken" in out
    assert "exit (3)" in out
