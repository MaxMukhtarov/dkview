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
    if os.name != "nt":
        return True
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        return bool(kernel32.SetConsoleMode(handle, mode.value | 0x0004))
    except Exception:
        return False


# for consoles on legacy code pages
ASCII = str.maketrans({
    "┌": "+", "┬": "+", "┐": "+", "├": "+", "┼": "+", "┤": "+", "└": "+", "┴": "+",
    "┘": "+", "─": "-", "│": "|", "●": "*", "○": "o", "✓": "OK", "✗": "X",
    "·": "-", "…": "~", "×": "x", "→": "->", "⚠": "!",
})


class _AsciiWriter:

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
    return text + " " * max(0, width - visible_len(text))


def terminal_size() -> "os.terminal_size":
    return shutil.get_terminal_size((120, 40))


def terminal_width() -> int:
    return terminal_size().columns
