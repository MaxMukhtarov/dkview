import re

import pytest

from pprint_docker.ansi import colors, strip
from pprint_docker.layout import choose_widths, render, wrap_cell
from pprint_docker.styles import styler
from pprint_docker.table import Table, parse_aligned

SAMPLES = [
    "registry.universalbank.uz/universalbank/transfers/api-v2:dev-e55edc11695bf0e572164ed49ea7a640b3a1b434",
    '"dotnet Universal.Transfers.Api.dll"',
    "0.0.0.0:80->80/tcp, :::443->443/tcp",
    "784KiB / 15.72GiB",
    "a",
    "",
]


@pytest.mark.parametrize("width", [1, 3, 5, 10, 17, 38, 200])
@pytest.mark.parametrize("value", SAMPLES)
def test_wrap_never_overflows_or_loses_text(value, width):
    lines = wrap_cell(value, width)
    assert all(len(line) <= width for line in lines)
    assert "".join(lines).replace(" ", "") == value.replace(" ", "")


def test_wrap_prefers_spaces():
    assert wrap_cell("784KiB / 15.72GiB", 14) == ["784KiB /", "15.72GiB"]


def test_wrap_breaks_paths_after_separators():
    lines = wrap_cell("registry.example.uz/team/api:v1", 22)
    assert lines == ["registry.example.uz/", "team/api:v1"]


def test_short_columns_keep_full_width():
    table = Table(
        ["ID", "IMAGE", "CREATED", "STATUS"],
        [["abc", "x" * 200, "4 minutes ago", "Up 4 minutes (healthy)"]],
    )
    widths = choose_widths(table, 100)
    assert widths[2] == len("4 minutes ago")
    assert widths[3] == len("Up 4 minutes (healthy)")
    assert sum(widths) + 3 * 4 + 1 <= 100


def test_every_line_has_the_requested_width_with_colors(fixture_lines):
    colors.enabled = True
    try:
        table = parse_aligned(fixture_lines("ps_screenshot.txt"))
        out = render(table, 100, styler)
        assert "\x1b[" in out
        assert {len(strip(line)) for line in out.splitlines()} == {100}
    finally:
        colors.enabled = False


def test_headers_line_up_with_columns(fixture_lines):
    colors.enabled = True
    try:
        table = parse_aligned(fixture_lines("ps_screenshot.txt"))
        lines = [strip(line) for line in render(table, 150).splitlines()]
        bars = [[m.start() for m in re.finditer("[│┌┬┐├┼┤└┴┘]", line)] for line in lines[:4]]
        assert bars[0] == bars[1] == bars[2] == bars[3]
    finally:
        colors.enabled = False


def test_empty_table_says_so():
    out = render(Table(["DRIVER", "VOLUME NAME"]), 60)
    lines = out.splitlines()
    assert "nothing to show" in out
    assert len({len(line) for line in lines}) == 1
