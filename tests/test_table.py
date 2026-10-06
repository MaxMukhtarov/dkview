from pprint_docker.table import parse, parse_aligned


def test_empty_ports_cell_stays_in_its_column(fixture_lines):
    # The bug from the original screenshot: NAMES slid into PORTS.
    table = parse_aligned(fixture_lines("ps_screenshot.txt"))
    ports = table.column("PORTS")
    names = table.column("NAMES")
    assert table.rows[1][ports] == ""
    assert table.rows[1][names] == "api-v2_transfers-v2-consumer.1.mjd483b1el2g51jq614djwe2j"
    assert table.rows[0][ports] == "7100/tcp"


def test_multi_word_headers(fixture_lines):
    table = parse_aligned(fixture_lines("ps_screenshot.txt"))
    assert table.headers[0] == "CONTAINER ID"
    assert len(table.headers) == 7
    assert all(len(row) == 7 for row in table.rows)


def test_right_aligned_size_columns(fixture_lines):
    # docker 29 `images` right-aligns DISK USAGE and CONTENT SIZE.
    table = parse_aligned(fixture_lines("images_v29.txt"))
    assert table.headers == ["IMAGE", "ID", "DISK USAGE", "CONTENT SIZE", "EXTRA"]
    sizes = [row[table.column("DISK USAGE")] for row in table.rows]
    assert all(s.endswith("B") for s in sizes)
    assert all(row[table.column("ID")] and len(row[1]) == 12 for row in table.rows)


def test_service_ls_with_empty_ports(fixture_lines):
    table = parse_aligned(fixture_lines("service_ls.txt"))
    broken = next(r for r in table.rows if r[1] == "broken")
    assert broken[table.column("REPLICAS")] == "0/1"
    assert broken[table.column("PORTS")] == ""


def test_value_wider_than_its_header():
    lines = [
        "ID   NAME   MODE",
        "1    a-very-long-service-name   global",
        "2    b      replicated",
    ]
    # Not tabwriter-aligned on purpose: the long name overflows NAME.
    table = parse_aligned(lines)
    assert [r[0] for r in table.rows] == ["1", "2"]


def test_header_only_output():
    table = parse(["DRIVER    VOLUME NAME"])
    assert table.headers == ["DRIVER", "VOLUME NAME"]
    assert table.rows == []


def test_not_a_table():
    assert parse(["hello"]) is None
