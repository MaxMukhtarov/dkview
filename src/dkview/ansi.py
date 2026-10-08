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


def _enable_windows_ansi() -> bool:
    """Windows 10+ consoles understand color codes once asked to.

    Returns False when they can't (old Windows), so colors stay off there.
    """
    if os.name != "nt":
        return True
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.GetStdHandle(-11)  # stdout
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))
    except Exception:
        return False


# Plain-ASCII stand-ins, for outputs that can't show box drawing or symbols
# (a pipe or an old console on Windows that uses a legacy code page).
# Characters that can sit inside a table cell map to one character.
ASCII = str.maketrans({
    "┌": "+", "┬": "+", "┐": "+", "├": "+", "┼": "+", "┤": "+", "└": "+", "┴": "+",
    "┘": "+", "─": "-", "│": "|", "●": "*", "○": "o", "✓": "OK", "✗": "X",
    "·": "-", "…": "~", "×": "x", "→": "->", "⚠": "!",
})


class _AsciiWriter:
    """Wraps a text stream, writing ASCII stand-ins for what it can't encode."""

    def __init__(self, stream) -> None:
        self._stream = stream

    def write(self, text: str) -> int:
        return self._stream.write(text.translate(ASCII))

    def __getattr__(self, name: str):
        return getattr(self._stream, name)


def _can_show(stream, sample: str = "┌─●✓") -> bool:
    try:
        sample.encode(getattr(stream, "encoding", None) or "ascii")
        return True
    except (LookupError, UnicodeEncodeError):
        return False


def prepare_output() -> None:
    """Never crash on a character the output's encoding lacks: use ASCII
    stand-ins for box lines and symbols, and '?' for anything else."""
    for name in ("stdout", "stderr"):
        stream = getattr(sys, name)
        if stream is None or _can_show(stream):
            continue
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="replace")
            except (ValueError, OSError):
                pass
        setattr(sys, name, _AsciiWriter(stream))


class _Colors:
    """Process-wide switch for colored output."""

    def __init__(self) -> None:
        self.enabled = (sys.stdout.isatty() and "NO_COLOR" not in os.environ
                        and _enable_windows_ansi())


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
