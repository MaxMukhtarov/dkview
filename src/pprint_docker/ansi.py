"""Terminal colors and helpers that measure text without escape codes."""

from __future__ import annotations

import os
import re
import shutil
import sys

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
REVERSE = "\033[7m"

ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


class _Colors:
    """Process-wide switch for colored output."""

    def __init__(self) -> None:
        self.enabled = sys.stdout.isatty() and "NO_COLOR" not in os.environ


colors = _Colors()


def paint(text: str, *codes: str) -> str:
    if not colors.enabled or not text or not codes:
        return text
    return "".join(codes) + text + RESET


def strip(text: str) -> str:
    return ANSI_RE.sub("", text)


def visible_len(text: str) -> int:
    return len(strip(text))


def pad(text: str, width: int) -> str:
    """ljust that ignores ANSI escape codes when measuring."""
    return text + " " * max(0, width - visible_len(text))


def terminal_size() -> "os.terminal_size":
    return shutil.get_terminal_size((120, 40))


def terminal_width() -> int:
    return terminal_size().columns
