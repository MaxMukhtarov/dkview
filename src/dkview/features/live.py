from __future__ import annotations

import sys
import time
from datetime import datetime
from typing import Callable

from ..ansi import DIM, BOLD, paint, terminal_size

ALT_SCREEN_ON = "\033[?1049h\033[?25l"
ALT_SCREEN_OFF = "\033[?25h\033[?1049l"
HOME = "\033[H"
CLEAR_LINE = "\033[K"
CLEAR_BELOW = "\033[J"


def run(frame: Callable[[int], str], title: str, interval: float) -> int:
    if not sys.stdout.isatty():
        sys.stdout.write(frame(terminal_size().columns))
        return 0

    out = sys.stdout
    out.write(ALT_SCREEN_ON)
    try:
        while True:
            started = time.monotonic()
            size = terminal_size()
            body = frame(size.columns).rstrip("\n").split("\n")

            stamp = datetime.now().strftime("%H:%M:%S")
            header = (paint(title, BOLD) + "  "
                      + paint(f"every {interval:g}s · {stamp} · Ctrl+C to quit", DIM))

            room = max(1, size.lines - 2)
            if len(body) > room:
                hidden = len(body) - room + 1
                body = body[:room - 1] + [paint(f"… {hidden} more lines (make the window taller)", DIM)]

            out.write(HOME + header + CLEAR_LINE + "\n" + CLEAR_LINE + "\n")
            out.write("\n".join(line + CLEAR_LINE for line in body))
            out.write(CLEAR_BELOW)
            out.flush()

            time.sleep(max(0.0, interval - (time.monotonic() - started)))
    except KeyboardInterrupt:
        return 0
    finally:
        out.write(ALT_SCREEN_OFF)
        out.flush()
