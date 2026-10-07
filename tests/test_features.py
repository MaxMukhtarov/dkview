import json
import re

import pytest

from pprint_docker.ansi import colors, strip
from pprint_docker.features import inspect, logs

FIXTURES = __import__("pathlib").Path(__file__).parent / "fixtures"


@pytest.mark.parametrize("line, level", [
    ("ERROR failed to connect", "error"),
    ("2026-10-06 12:00:00 [warn] disk almost full", "warn"),
    ('{"level":"info","msg":"started"}', "info"),
    ("time=x level=debug msg=hi", "debug"),
    ("panic: runtime error", "error"),
    ("plain line", None),
])
def test_log_levels(line, level):
    assert logs.level_of(line) == level


def test_log_coloring_keeps_text_and_highlights_grep():
    colors.enabled = True
    try:
        out = logs.colorize("web-1  | 2026-10-06T08:00:00Z WARN slow query",
                            re.compile("slow", re.I))
        assert strip(out) == "web-1  | 2026-10-06T08:00:00Z WARN slow query"
        assert "\x1b[7m" in out  # highlighted match
    finally:
        colors.enabled = False


def test_container_summary():
    data = json.loads((FIXTURES / "inspect_containers.json").read_text())
    title, sections = inspect.container_summary(data[0])
    overview = dict(sections[0][1])
    assert title.startswith("web")
    assert overview["Status"] == "running (healthy)"
    assert overview["ID"] == data[0]["Id"][:12]
    ports = dict(next(s for s in sections if s[0] == "Ports")[1])
    assert ports == {"0.0.0.0:8080": "→ 80/tcp"}


def test_unhealthy_container_shows_last_check():
    data = json.loads((FIXTURES / "inspect_containers.json").read_text())
    _, sections = inspect.container_summary(data[1])
    overview = dict(sections[0][1])
    assert "unhealthy" in overview["Status"]
    assert "Last health check" in overview


def test_service_summary():
    data = json.loads((FIXTURES / "inspect_service.json").read_text())
    title, sections = inspect.service_summary(data[0])
    overview = dict(sections[0][1])
    assert title.startswith("api")
    assert overview["Mode"] == "replicated, 2 replicas"
    assert "@sha256" not in overview["Image"]


def test_unknown_objects_fall_back_to_tree():
    data = json.loads((FIXTURES / "inspect_network.json").read_text())
    assert inspect.kind_of(data[0]) is None
    lines = inspect.tree(data[0])
    assert any(line.startswith("├─ Name: bridge") for line in lines)


def test_tree_shape():
    lines = inspect.tree({"a": 1, "b": {"c": [1, 2], "d": None}})
    assert lines == ["├─ a: 1", "└─ b", "   ├─ c: [1, 2]", "   └─ d: null"]


def test_mark_in_use_handles_both_image_layouts():
    from pprint_docker.features.images import mark_in_use
    from pprint_docker.table import Table

    legacy = Table(["REPOSITORY", "TAG", "IMAGE ID"], [["alpine", "latest", "294b683cb724"],
                                                      ["busybox", "latest", "fd7dc98638c8"]])
    assert mark_in_use(legacy, {"294b683cb724"})
    assert [r[0] for r in legacy.rows] == ["● alpine", "○ busybox"]

    v29 = Table(["IMAGE", "ID", "DISK USAGE"], [["alpine:latest", "294b683cb724", "13MB"]])
    assert mark_in_use(v29, set())
    assert v29.rows[0][0] == "○ alpine:latest"

    assert not mark_in_use(Table(["NAME", "DRIVER"], [["x", "y"]]), set())


def test_in_use_dot_is_green():
    from pprint_docker.ansi import GREEN
    from pprint_docker.layout import render
    from pprint_docker.table import Table

    colors.enabled = True
    try:
        out = render(Table(["REPOSITORY"], [["● alpine"]]), 40)
        assert GREEN + "●" in out
    finally:
        colors.enabled = False
