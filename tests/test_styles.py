import pytest

from dkview.ansi import DIM, GREEN, RED, YELLOW
from dkview.styles import styler


@pytest.mark.parametrize("header, value, color", [
    ("STATUS", "Up 4 minutes (healthy)", GREEN),
    ("STATUS", "Up 4 minutes", GREEN),
    ("STATUS", "Up 9 seconds (unhealthy)", RED),
    ("STATUS", "Up 2 seconds (health: starting)", YELLOW),
    ("STATUS", "Exited (0) 3 hours ago", DIM),
    ("STATUS", "Exited (137) 3 hours ago", RED),
    ("STATUS", "Restarting (1) 5 seconds ago", YELLOW),
    ("STATUS", "Ready", GREEN),          # docker node ls
    ("STATUS", "Down", RED),
    ("REPLICAS", "2/2", GREEN),
    ("REPLICAS", "1/3", YELLOW),
    ("REPLICAS", "0/1", RED),
    ("REPLICAS", "1/1 (max 1 per node)", GREEN),
    ("CURRENT STATE", "Running 5 minutes ago", GREEN),
    ("CURRENT STATE", "Rejected 4 seconds ago", RED),
    ("CURRENT STATE", "Shutdown 1 hour ago", DIM),
    ("AVAILABILITY", "Drain", YELLOW),
    ("CPU %", "95.10%", RED),
    ("CPU %", "60%", YELLOW),
    ("CPU %", "2.10%", None),
    ("ERROR", "no suitable node", RED),
    ("PORTS", "80/tcp", None),
])
def test_cell_colors(header, value, color):
    assert styler(header, value) == color


def test_empty_cells_are_plain():
    assert styler("STATUS", "") is None
