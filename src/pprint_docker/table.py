"""The Table model and parsers that turn command output into one."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from .ansi import strip


@dataclass
class Table:
    headers: List[str]
    rows: List[List[str]] = field(default_factory=list)

    def column(self, name: str) -> Optional[int]:
        """Index of the column with this exact header (case-insensitive)."""
        name = name.upper()
        for i, header in enumerate(self.headers):
            if header.upper() == name:
                return i
        return None


# A header is a run of words separated by single spaces ("CONTAINER ID");
# columns are separated by two or more spaces.
_HEADER_RE = re.compile(r"\S+(?: \S+)*")


def parse_aligned(lines: Sequence[str]) -> Optional[Table]:
    """Parse column-aligned output (docker, kubectl, any Go tabwriter).

    Column boundaries come from the header's positions, adjusted to the
    nearest character position that is blank on every row. That keeps
    empty cells in place (a container with no PORTS) and also handles
    right-aligned columns such as SIZE in newer `docker images`.
    """
    lines = [strip(line).rstrip() for line in lines]

    header_index = next(
        (i for i, line in enumerate(lines)
         if line.strip() and re.search(r"\S\s{2,}\S", line)),
        None,
    )
    if header_index is None:
        return None

    header_line = lines[header_index]
    spans = [(m.start(), m.end()) for m in _HEADER_RE.finditer(header_line)]
    if len(spans) < 2:
        return None

    body = [line for line in lines[header_index + 1:] if line.strip()]
    bounds = _column_bounds(spans, body)

    rows = [_slice(line, bounds) for line in body]
    headers = [header_line[s:e] for s, e in spans]
    return Table(headers, rows)


def _column_bounds(spans: List[Tuple[int, int]], body: List[str]) -> List[int]:
    def blank(pos: int) -> bool:
        return all(pos >= len(line) or line[pos] == " " for line in body)

    bounds = [0]
    for (start, end), (next_start, next_end) in zip(spans, spans[1:]):
        # Prefer a blank position in the gap between the two headers,
        # closest to where the next header starts.
        candidates = range(next_start, end - 1, -1)
        boundary = next((p for p in candidates if blank(p)), None)

        if boundary is None:
            # A value overflows its header; look a bit further either way.
            wider = sorted(range(start + 1, next_end),
                           key=lambda p: abs(p - next_start))
            boundary = next((p for p in wider if blank(p)), next_start)

        bounds.append(max(boundary, bounds[-1]))
    return bounds


def _slice(line: str, bounds: List[int]) -> List[str]:
    edges = bounds + [max(len(line), bounds[-1])]
    return [line[edges[i]:edges[i + 1]].strip() for i in range(len(bounds))]


def parse_whitespace(lines: Sequence[str]) -> Optional[Table]:
    """Fallback for output whose columns are separated by single spaces."""
    lines = [strip(line).rstrip() for line in lines if line.strip()]
    if len(lines) < 2:
        return None

    headers = lines[0].split()
    if len(headers) < 2:
        return None

    rows = []
    for line in lines[1:]:
        parts = line.split(None, len(headers) - 1)
        if len(parts) != len(headers):
            return None
        rows.append(parts)
    return Table(headers, rows)


def parse(lines: Sequence[str]) -> Optional[Table]:
    return parse_aligned(lines) or parse_whitespace(lines)
