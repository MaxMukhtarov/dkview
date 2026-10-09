from __future__ import annotations

import re
from typing import Callable, List, Optional, Sequence

from .ansi import BOLD, DIM, GREEN, paint, pad, terminal_width, visible_len
from .table import Table

Styler = Callable[[str, str], Optional[str]]

MARKERS = {"●": GREEN, "○": DIM}

SOFT_BREAK_CHARS = "/:-_.,@>"
_breaks = re.escape(SOFT_BREAK_CHARS)
_PIECE_RE = re.compile(rf"[^{_breaks}]*[{_breaks}]+|[^{_breaks}]+")


def wrap_cell(value: str, width: int) -> List[str]:
    text = " ".join(str(value).split())
    if width <= 0 or not text:
        return [""]

    lines: List[str] = []
    line = ""
    for word in text.split(" "):
        joined = f"{line} {word}" if line else word
        if len(joined) <= width:
            line = joined
            continue
        if len(word) <= width:
            lines.append(line)
            line = word
            continue

        for n, piece in enumerate(_PIECE_RE.findall(word)):
            joiner = " " if n == 0 and line else ""
            if len(line + joiner + piece) <= width:
                line += joiner + piece
                continue
            if len(piece) <= width:
                if line:
                    lines.append(line)
                line = piece
                continue
            line += joiner + piece
            while len(line) > width:
                lines.append(line[:width])
                line = line[width:]

    if line or not lines:
        lines.append(line)
    return lines


def has_marker(value: str) -> bool:
    return value[:1] in MARKERS and value[1:2] == " "


def wrap_marked(value: str, width: int) -> List[str]:
    if not has_marker(value) or width <= 3:
        return wrap_cell(value, width)
    lines = wrap_cell(value[2:], width - 2)
    return [value[:2] + lines[0]] + ["  " + line for line in lines[1:]]


def choose_widths(table: Table, max_width: int) -> List[int]:
    count = len(table.headers)
    natural = []
    for i in range(count):
        values = [table.headers[i]] + [row[i] for row in table.rows]
        natural.append(max(1, max(visible_len(v) for v in values)))

    available = max_width - (3 * count + 1)
    if sum(natural) <= available:
        return natural

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

    for i in sorted(range(count), key=lambda i: natural[i] - widths[i],
                    reverse=True):
        if remaining <= 0:
            break
        extra = min(remaining, natural[i] - widths[i])
        widths[i] += extra
        remaining -= extra

    return widths


def render(table: Table, width: Optional[int] = None,
           styler: Optional[Styler] = None) -> str:
    if not table.headers:
        return ""

    widths = choose_widths(table, width or terminal_width())

    def line(left: str, middle: str, right: str) -> str:
        return paint(left + middle.join("─" * (w + 2) for w in widths) + right, DIM)

    bar = paint("│", DIM)

    def draw(cells: Sequence[str], header: bool = False) -> List[str]:
        wrapped = [wrap_marked(cells[i], widths[i]) for i in range(len(widths))]
        codes = [
            BOLD if header else (styler(table.headers[i], cells[i]) if styler else None)
            for i in range(len(widths))
        ]
        marker_cells = [has_marker(c) for c in cells]
        out = []
        for n in range(max(len(c) for c in wrapped)):
            parts = []
            for i, cell_lines in enumerate(wrapped):
                value = cell_lines[n] if n < len(cell_lines) else ""
                marker = ""
                if value[:1] in MARKERS and value[1:2] == " ":
                    marker, value = paint(value[0], MARKERS[value[0]]) + " ", value[2:]
                elif n and marker_cells[i]:
                    marker, value = "  ", value[2:]
                if codes[i]:
                    value = paint(value, codes[i])
                value = marker + value
                parts.append(" " + pad(value, widths[i]) + " ")
            out.append(bar + bar.join(parts) + bar)
        return out

    output = [line("┌", "┬", "┐")]
    output += draw(table.headers, header=True)
    output.append(line("├", "┼", "┤"))
    for row in table.rows:
        output += draw(row)
    if not table.rows:
        inner = sum(widths) + 3 * len(widths) - 1
        output[-1] = line("├", "┴", "┤")
        output.append(bar + pad(" " + paint("nothing to show", DIM), inner) + bar)
        output.append(line("└", "─", "┘"))
        return "\n".join(output)
    output.append(line("└", "┴", "┘"))
    return "\n".join(output)


def render_plain_rows(rows: Sequence[Sequence[str]], gap: int = 2) -> List[str]:
    if not rows:
        return []
    widths = [max(visible_len(r[i]) for r in rows) for i in range(len(rows[0]))]
    return [
        (" " * gap).join(pad(c, widths[i]) for i, c in enumerate(r)).rstrip()
        for r in rows
    ]
