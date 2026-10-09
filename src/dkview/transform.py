from __future__ import annotations

import re
from typing import Sequence, Tuple

from .table import Table


ID_COLUMNS = {"ID", "CONTAINER ID", "IMAGE ID", "NETWORK ID", "CONTAINER"}
IMAGE_COLUMNS = {"IMAGE", "REPOSITORY"}
TIME_COLUMNS = {"CREATED", "STATUS", "CURRENT STATE", "CREATED AT", "SINCE",
                "RUNNING FOR", "UPDATED"}

_FULL_ID_RE = re.compile(r"^(sha256:)?[0-9a-f]{64}$|^[0-9a-z]{25}$")
_DIGEST_RE = re.compile(r"@sha256:[0-9a-f]{64}")

_UNITS = {
    "second": "s", "minute": "m", "hour": "h", "day": "d",
    "week": "w", "month": "mo", "year": "y",
}
_AGE_RE = re.compile(
    r"\b(?:about |almost |over )?(an?|\d+) (second|minute|hour|day|week|month|year)s?\b",
    re.IGNORECASE,
)


def compact_age(text: str) -> str:
    text = re.sub(r"\bless than a second\b", "<1s", text, flags=re.IGNORECASE)

    def repl(m: "re.Match[str]") -> str:
        count = "1" if m.group(1).lower() in ("a", "an") else m.group(1)
        return count + _UNITS[m.group(2).lower()]

    return _AGE_RE.sub(repl, text)


def short_image(image: str) -> str:
    first, sep, rest = image.partition("/")
    if sep and ("." in first or ":" in first or first == "localhost"):
        return rest
    return image


COMMAND_LIMIT = 60


def one_line(text: str) -> str:
    return " ".join(text.split())


_TASK_NAME_RE = re.compile(r"^(.+\.(?:\d+|[0-9a-z]{25}))\.[0-9a-z]{25}$")


def is_task_container(name: str) -> bool:
    return bool(_TASK_NAME_RE.match(name))


def short_task_name(name: str) -> str:
    m = _TASK_NAME_RE.match(name)
    return m.group(1) if m else name


def tidy(table: Table, *, humanize: bool, short: bool, strip_digests: bool,
         full: bool = False) -> None:
    for col, header in enumerate(h.upper() for h in table.headers):
        for row in table.rows:
            value = row[col]
            if _FULL_ID_RE.match(value) and (header in ID_COLUMNS or ":" in value
                                              or len(value) == 64):
                value = value.split(":")[-1][:12]
            if short and header in ("NAMES", "NAME"):
                value = ", ".join(short_task_name(n) for n in value.split(","))
            if header in IMAGE_COLUMNS:
                if strip_digests:
                    value = _DIGEST_RE.sub("", value)
                if short:
                    value = short_image(value)
            if header == "COMMAND":
                value = one_line(value)
                if not full and len(value) > COMMAND_LIMIT:
                    quote = '"' if value.startswith('"') else ""
                    keep = COMMAND_LIMIT - 1 - len(quote)
                    value = value[:keep].rstrip() + "…" + quote
            if humanize and header in TIME_COLUMNS:
                value = compact_age(value)
            row[col] = value


class ColumnError(ValueError):
    pass


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def find_column(table: Table, name: str) -> int:
    want = _norm(name)
    normed = [_norm(h) for h in table.headers]
    for test in (lambda h: h == want,
                 lambda h: h.startswith(want),
                 lambda h: h.endswith(want),
                 lambda h: want in h,
                 lambda h: _is_subsequence(want, h)):
        for i, h in enumerate(normed):
            if want and test(h):
                return i
    raise ColumnError(
        f"no column matches '{name}'. Columns: "
        + ", ".join(h.lower() for h in table.headers)
    )


def _is_subsequence(short: str, full: str) -> bool:
    rest = iter(full)
    return all(ch in rest for ch in short)


def select_columns(table: Table, names: Sequence[str]) -> Table:
    idx = [find_column(table, n) for n in names]
    return Table([table.headers[i] for i in idx],
                 [[row[i] for i in idx] for row in table.rows])


_SIZE_UNITS = {
    "b": 1, "kb": 1e3, "mb": 1e6, "gb": 1e9, "tb": 1e12,
    "kib": 1024, "mib": 1024 ** 2, "gib": 1024 ** 3, "tib": 1024 ** 4,
}
_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800,
            "mo": 2592000, "y": 31536000}


def sort_key(value: str) -> Tuple[int, float, str]:
    text = re.sub(r"^[●○] ", "", value.strip())
    low = compact_age(text).lower()

    m = re.match(r"^(-?\d+(?:\.\d+)?)\s*%", low)
    if m:
        return (0, float(m.group(1)), "")
    m = re.match(r"^(\d+(?:\.\d+)?)\s*([kmgt]?i?b)\b", low)
    if m:
        return (0, float(m.group(1)) * _SIZE_UNITS[m.group(2)], "")
    m = re.search(r"(?:^|\s)<?(\d+)(mo|[smhdwy])(?=\s|$)", low)
    if m:
        return (0, float(m.group(1)) * _SECONDS[m.group(2)], "")
    m = re.match(r"^-?\d+(?:\.\d+)?$", low)
    if m:
        return (0, float(low), "")
    m = re.match(r"^(\d+)/(\d+)", low)
    if m:
        total = int(m.group(2)) or 1
        return (0, int(m.group(1)) / total, "")
    return (1, 0.0, low)


def sort_rows(table: Table, column: str, descending: bool = False) -> None:
    i = find_column(table, column)
    table.rows.sort(key=lambda row: sort_key(row[i]), reverse=descending)


def grep_rows(table: Table, pattern: "re.Pattern[str]") -> None:
    table.rows = [row for row in table.rows if pattern.search("  ".join(row))]
