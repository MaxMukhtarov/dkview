import re

import pytest

from pprint_docker.table import Table
from pprint_docker.transform import (
    ColumnError, compact_age, find_column, grep_rows, select_columns,
    short_image, sort_key, sort_rows, tidy,
)


@pytest.mark.parametrize("raw, short", [
    ("4 minutes ago", "4m ago"),
    ("Up 29 hours (healthy)", "Up 29h (healthy)"),
    ("About an hour ago", "1h ago"),
    ("Up About a minute", "Up 1m"),
    ("Less than a second ago", "<1s ago"),
    ("Exited (1) 2 days ago", "Exited (1) 2d ago"),
    ("Running 3 weeks ago", "Running 3w ago"),
    ("5 months ago", "5mo ago"),
    ("Created", "Created"),
])
def test_compact_age(raw, short):
    assert compact_age(raw) == short


@pytest.mark.parametrize("image, short", [
    ("registry.doublewave.uz/doublewave/transfers/api-v2:dev", "doublewave/transfers/api-v2:dev"),
    ("localhost:5000/app:1", "app:1"),
    ("localhost/app", "app"),
    ("library/alpine:3", "library/alpine:3"),
    ("alpine", "alpine"),
])
def test_short_image(image, short):
    assert short_image(image) == short


def test_tidy_shortens_ids_and_digests():
    table = Table(["CONTAINER ID", "IMAGE", "ID"], [[
        "26a04fd7c376e7815b3104433bd54c3ec419a559cc55a364b935664ae44bd874",
        "alpine:latest@sha256:294b683cb724975bec92580e1e685676bd4b50bda910ddb8c51d4cabeaec77e6",
        "s5jbcywkcic84sn8h8563iwv8",
    ]])
    tidy(table, humanize=True, short=False, strip_digests=True)
    assert table.rows[0] == ["26a04fd7c376", "alpine:latest", "s5jbcywkcic8"]


TABLE = Table(["CONTAINER ID", "NAME", "CPU %", "MEM USAGE / LIMIT", "CREATED"], [
    ["a", "web", "2.10%", "1.172MiB / 15GiB", "2 days ago"],
    ["b", "db", "15.5%", "512MiB / 15GiB", "4 minutes ago"],
    ["c", "cache", "0.00%", "900KiB / 15GiB", "About an hour ago"],
])


@pytest.mark.parametrize("name, header", [
    ("cpu", "CPU %"), ("mem", "MEM USAGE / LIMIT"), ("id", "CONTAINER ID"),
    ("NAME", "NAME"), ("crt", "CREATED"),
])
def test_find_column(name, header):
    assert TABLE.headers[find_column(TABLE, name)] == header


def test_unknown_column_lists_choices():
    with pytest.raises(ColumnError, match="container id, name"):
        find_column(TABLE, "bogus")


def test_select_columns_reorders():
    picked = select_columns(TABLE, ["name", "cpu"])
    assert picked.headers == ["NAME", "CPU %"]
    assert picked.rows[0] == ["web", "2.10%"]


def _sorted(column, desc=False):
    t = Table(TABLE.headers, [list(r) for r in TABLE.rows])
    sort_rows(t, column, desc)
    return [r[1] for r in t.rows]


def test_sort_by_percent_size_and_age():
    assert _sorted("cpu", desc=True) == ["db", "web", "cache"]
    assert _sorted("mem") == ["cache", "web", "db"]
    assert _sorted("created") == ["db", "cache", "web"]


def test_sort_key_does_not_treat_names_as_ages():
    assert sort_key("web-2d")[0] == 1


def test_grep_rows():
    t = Table(TABLE.headers, [list(r) for r in TABLE.rows])
    grep_rows(t, re.compile("WEB|cache", re.IGNORECASE))
    assert [r[1] for r in t.rows] == ["web", "cache"]


def test_sort_ignores_image_marks():
    t = Table(["REPOSITORY"], [["○ alpine"], ["● busybox"]])
    sort_rows(t, "repository")
    assert [r[0] for r in t.rows] == ["○ alpine", "● busybox"]
