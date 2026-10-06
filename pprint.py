#!/usr/bin/env python3
"""Run a command and pretty-print its tabular output as a boxed table.

    pprint docker ps
    pprint docker service ls
    pprint --width 120 docker images
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple


RESET = "\033[0m"
BOLD = "\033[1m"

USE_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None

ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")

# Characters after which a long token (image names, paths, port lists)
# may be broken when it does not fit in its column.
SOFT_BREAK_CHARS = "/:-_.,@>"

# Columns that hold docker IDs; full 64-char hex IDs are shortened to 12.
ID_COLUMNS = {"ID", "CONTAINER ID", "IMAGE ID", "NETWORK ID"}
FULL_ID_RE = re.compile(r"^(sha256:)?[0-9a-f]{64}$")

# docker global options that take a value (used to find the subcommand).
DOCKER_VALUE_OPTS = {
    "-c", "--context", "-H", "--host", "--config", "-l", "--log-level",
    "--tlscacert", "--tlscert", "--tlskey",
}


@dataclass
class Table:
    headers: List[str]
    rows: List[List[str]]


def color(text: str, code: str) -> str:
    if not USE_COLOR:
        return text
    return f"{code}{text}{RESET}"


def visible_len(text: str) -> int:
    return len(ANSI_RE.sub("", text))


def pad(text: str, width: int) -> str:
    """ljust that ignores ANSI escape codes when measuring."""
    return text + " " * max(0, width - visible_len(text))


def terminal_width() -> int:
    try:
        return shutil.get_terminal_size((120, 24)).columns
    except Exception:
        return 120


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------

def split_docker_table(lines: List[str]) -> Optional[Table]:
    """Parse docker's column-aligned output using the header's offsets.

    docker pads every column to a fixed width, so each header's start
    position is also where that column's values start. Slicing by those
    offsets keeps empty cells (e.g. a container with no PORTS) in place,
    which splitting on runs of spaces cannot do.
    """
    lines = [ANSI_RE.sub("", line.rstrip()) for line in lines]

    header_index = next(
        (
            i for i, line in enumerate(lines)
            if line.strip() and re.search(r"\S\s{2,}\S", line)
        ),
        None,
    )
    if header_index is None:
        return None

    header_line = lines[header_index]
    # A header is a run of words separated by single spaces
    # ("CONTAINER ID"); columns are separated by two or more spaces.
    matches = list(re.finditer(r"\S+(?: \S+)*", header_line))
    if len(matches) < 2:
        return None

    headers = [m.group() for m in matches]
    starts = [m.start() for m in matches]

    rows: List[List[str]] = []
    for line in lines[header_index + 1:]:
        if not line.strip():
            continue
        rows.append(slice_row(line, starts))

    return Table(headers, rows)


def slice_row(line: str, starts: List[int]) -> List[str]:
    # If a value ever runs past the next header's offset, move that
    # boundary forward to the next whitespace instead of cutting the word.
    bounds = []
    for start in starts:
        while 0 < start < len(line) and not line[start - 1].isspace():
            start += 1
        bounds.append(start)
    bounds.append(len(line))

    cells = []
    for i in range(len(starts)):
        lo = bounds[i]
        hi = max(lo, bounds[i + 1])
        cells.append(line[lo:hi].strip())
    return cells


def split_generic(lines: List[str]) -> Optional[Table]:
    lines = [line.rstrip() for line in lines if line.strip()]
    if len(lines) < 2:
        return None

    headers = re.split(r"\s+", lines[0].strip())
    if len(headers) < 2:
        return None

    rows: List[List[str]] = []
    for line in lines[1:]:
        parts = re.split(r"\s+", line.strip(), maxsplit=len(headers) - 1)
        if len(parts) != len(headers):
            return None
        rows.append(parts)

    return Table(headers, rows)


def shorten_ids(table: Table) -> None:
    for col, header in enumerate(table.headers):
        if header.upper() not in ID_COLUMNS:
            continue
        for row in table.rows:
            value = row[col]
            if FULL_ID_RE.match(value):
                row[col] = value.split(":")[-1][:12]


# --------------------------------------------------------------------------
# Layout
# --------------------------------------------------------------------------

def wrap_cell(value: str, width: int) -> List[str]:
    """Wrap text, preferring spaces, then '/', ':', '-' etc., then hard cuts."""
    text = " ".join(str(value).split())
    if width <= 0 or not text:
        return [""]

    # Split into pieces that each end at a space or just after a separator,
    # then fill lines greedily with whole pieces.
    breaks = re.escape(SOFT_BREAK_CHARS)
    pieces = re.findall(rf"[^ {breaks}]*[{breaks}]+ ?|[^ {breaks}]+ ?| ", text)

    lines: List[str] = []
    line = ""
    for piece in pieces:
        if len(line + piece.rstrip()) <= width:
            line += piece
            continue
        if len(piece.rstrip()) > width:
            # Too long for any line (e.g. a hash): it will be cut anyway,
            # so start it on the current line rather than wasting space.
            line += piece
        else:
            if line.strip():
                lines.append(line.rstrip())
            line = piece
        # A single piece wider than the column has to be cut.
        while len(line.rstrip()) > width:
            lines.append(line[:width])
            line = line[width:]

    if line.strip() or not lines:
        lines.append(line.rstrip())
    return lines


def choose_widths(table: Table, max_width: int) -> List[int]:
    """Fit columns into max_width using max-min fairness.

    Columns are visited from narrowest to widest. Each gets either its
    natural width or an equal share of what is left, whichever is
    smaller. Short columns (CREATED, STATUS, PORTS) therefore keep their
    full width, and only the genuinely long ones (IMAGE, COMMAND, NAMES)
    are wrapped, sharing the remaining space evenly.
    """
    count = len(table.headers)

    natural = []
    for i in range(count):
        values = [table.headers[i]] + [row[i] for row in table.rows]
        natural.append(max(1, max(visible_len(v) for v in values)))

    # "│ " before each cell, " " after, plus the closing "│".
    overhead = 3 * count + 1
    available = max_width - overhead

    if sum(natural) <= available:
        return natural

    # A column never gets narrower than its longest header word or 6.
    floors = [
        min(natural[i], max(6, *(len(w) for w in table.headers[i].split())))
        for i in range(count)
    ]
    available = max(available, sum(floors))

    widths = [0] * count
    remaining = available
    order = sorted(range(count), key=lambda i: natural[i])
    for n, i in enumerate(order):
        share = remaining // (count - n)
        widths[i] = max(floors[i], min(natural[i], share))
        remaining -= widths[i]

    # Hand any rounding leftovers to columns that still want more.
    for i in sorted(range(count), key=lambda i: natural[i] - widths[i],
                    reverse=True):
        if remaining <= 0:
            break
        extra = min(remaining, natural[i] - widths[i])
        widths[i] += extra
        remaining -= extra

    return widths


def render(table: Table, width: Optional[int] = None) -> str:
    if not table.headers:
        return ""

    widths = choose_widths(table, width or terminal_width())

    def border(left: str, middle: str, right: str) -> str:
        return left + middle.join("─" * (w + 2) for w in widths) + right

    def draw_row(cells: Sequence[str], style: Optional[str] = None) -> List[str]:
        wrapped = [wrap_cell(cells[i], widths[i]) for i in range(len(widths))]
        height = max(len(c) for c in wrapped)
        out = []
        for n in range(height):
            parts = []
            for i, lines in enumerate(wrapped):
                value = lines[n] if n < len(lines) else ""
                if style and value:
                    value = color(value, style)
                parts.append(" " + pad(value, widths[i]) + " ")
            out.append("│" + "│".join(parts) + "│")
        return out

    output = [border("┌", "┬", "┐")]
    output += draw_row(table.headers, BOLD)
    output.append(border("├", "┼", "┤"))
    for row in table.rows:
        output += draw_row(row)
    output.append(border("└", "┴", "┘"))
    return "\n".join(output)


# --------------------------------------------------------------------------
# Command handling
# --------------------------------------------------------------------------

def run_command(argv: Sequence[str]) -> Tuple[int, str, str]:
    try:
        process = subprocess.run(
            argv,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return process.returncode, process.stdout, process.stderr
    except FileNotFoundError:
        return 127, "", f"{argv[0]}: command not found\n"
    except KeyboardInterrupt:
        return 130, "", ""


def is_docker(argv: Sequence[str]) -> bool:
    return bool(argv) and os.path.basename(argv[0]) in {"docker", "docker.exe"}


def docker_subcommand(argv: Sequence[str]) -> List[str]:
    """Return the non-option words after `docker`, e.g. ['container', 'ls']."""
    words: List[str] = []
    skip = False
    for arg in argv[1:]:
        if skip:
            skip = False
            continue
        if arg in DOCKER_VALUE_OPTS:
            skip = True
            continue
        if arg.startswith("-"):
            if words:
                break
            continue
        words.append(arg)
        if len(words) == 2:
            break
    return words


def add_no_trunc(argv: List[str]) -> List[str]:
    """Ask `docker ps` for full values so COMMAND is not cut to 20 chars.

    Skipped when the user already chose an output shape themselves.
    """
    words = docker_subcommand(argv)
    is_ps = words[:1] == ["ps"] or (
        words[:1] == ["container"] and words[1:2] in (["ls"], ["ps"], ["list"])
    )
    if not is_ps:
        return argv

    chosen = {"--no-trunc", "--format", "-q", "--quiet"}
    if any(a in chosen or a.startswith("--format=") for a in argv):
        return argv

    return argv + ["--no-trunc"]


def main() -> int:
    global USE_COLOR

    parser = argparse.ArgumentParser(
        prog="pprint",
        description="Pretty-print command output as terminal tables.",
    )
    parser.add_argument("--width", type=int, default=None,
                        help="Override terminal table width.")
    parser.add_argument("--no-color", action="store_true",
                        help="Disable colors.")
    parser.add_argument("--raw", action="store_true",
                        help="Run command without formatting.")
    parser.add_argument("--trunc", action="store_true",
                        help="Keep docker's own truncation of long values.")
    parser.add_argument("command", nargs=argparse.REMAINDER,
                        help="Command to execute.")

    args = parser.parse_args()

    if args.no_color:
        USE_COLOR = False

    if not args.command:
        parser.print_help()
        return 2

    command = list(args.command)
    docker = is_docker(command)
    if docker and not args.raw and not args.trunc:
        command = add_no_trunc(command)

    return_code, stdout, stderr = run_command(command)

    if stderr:
        sys.stderr.write(stderr)

    if args.raw or not stdout.strip():
        sys.stdout.write(stdout)
        return return_code

    lines = stdout.splitlines()

    table = split_docker_table(lines) if docker else None
    if table is not None:
        shorten_ids(table)
    else:
        table = split_generic(lines)

    if table is None:
        sys.stdout.write(stdout)
        return return_code

    sys.stdout.write(render(table, args.width) + "\n")
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
