"""Sizes and times as docker prints them, and back."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

_SIZE_UNITS = {
    "b": 1, "kb": 1e3, "mb": 1e6, "gb": 1e9, "tb": 1e12,
    "kib": 1024, "mib": 1024 ** 2, "gib": 1024 ** 3, "tib": 1024 ** 4,
}


def parse_size(text: str) -> float:
    """'281MB' -> 281000000.0; unknown text -> 0."""
    m = re.match(r"^\s*(\d+(?:\.\d+)?)\s*([kmgt]?i?b)\b", text or "", re.IGNORECASE)
    if not m:
        return 0.0
    return float(m.group(1)) * _SIZE_UNITS[m.group(2).lower()]


def human_size(n: float) -> str:
    """Decimal units, like docker: 281000000 -> '281MB'."""
    size = float(n)
    for unit in ("B", "kB", "MB", "GB", "TB"):
        if size < 1000 or unit == "TB":
            if unit == "B":
                return f"{size:.0f}B"
            return f"{size:.3g}{unit}" if size < 100 else f"{size:.0f}{unit}"
        size /= 1000
    return ""


def parse_docker_time(text: str) -> Optional[datetime]:
    """'2026-09-17 20:37:20 +0000 UTC' -> aware datetime."""
    m = re.match(r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) ([+-]\d{4})", text or "")
    if not m:
        return None
    return datetime.strptime(f"{m.group(1)} {m.group(2)}", "%Y-%m-%d %H:%M:%S %z")


def ago(when: Optional[datetime], now: Optional[datetime] = None) -> str:
    if when is None:
        return ""
    now = now or datetime.now(timezone.utc)
    seconds = max(0, int((now - when).total_seconds()))
    for unit, size in (("y", 31536000), ("mo", 2592000), ("w", 604800), ("d", 86400),
                       ("h", 3600), ("m", 60), ("s", 1)):
        if seconds >= size:
            return f"{seconds // size}{unit} ago"
    return "just now"
