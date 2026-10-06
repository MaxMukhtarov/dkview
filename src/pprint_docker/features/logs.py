"""`docker logs` with lines colored by level and an optional --grep filter."""

from __future__ import annotations

import re
import subprocess
import sys
import zlib
from typing import Optional, Sequence

from ..ansi import BLUE, BOLD, CYAN, DIM, GREEN, MAGENTA, RED, REVERSE, YELLOW, colors, paint
from ..options import Options

_LEVEL_RE = re.compile(
    r"\b(FATAL|PANIC|CRIT(?:ICAL)?|ERROR|ERR|EROR|FAIL(?:ED|URE)?|WARN(?:ING)?|WRN|"
    r"INFO|INF|NOTICE|DEBUG|DBG|TRACE|TRC)\b"
    # level=error, "level":"warn", [error]
    r"|\blevel\s*[=:]\s*\"?(\w+)"
    r"|\"(?:level|severity)\"\s*:\s*\"(\w+)\""
    r"|\[(error|warn(?:ing)?|info|debug)\]",
    re.IGNORECASE,
)

_LEADING_TIME_RE = re.compile(
    r"^(\d{4}-\d\d-\d\d[T ]\d\d:\d\d:\d\d(?:[.,]\d+)?(?:Z|[+-]\d\d:?\d\d)?)"
)

# `docker compose logs` prefixes each line with "service-1  | ".
_COMPOSE_PREFIX_RE = re.compile(r"^(\S+\s+\| )")
_PREFIX_COLORS = [CYAN, MAGENTA, BLUE, GREEN, YELLOW]


def level_of(line: str) -> Optional[str]:
    m = _LEVEL_RE.search(line)
    if not m:
        return None
    word = next(g for g in m.groups() if g).lower()
    if word.startswith(("fatal", "panic", "crit", "err", "eror", "fail")):
        return "error"
    if word.startswith(("warn", "wrn")):
        return "warn"
    if word.startswith(("info", "inf", "notice")):
        return "info"
    if word.startswith(("debug", "dbg", "trace", "trc")):
        return "debug"
    return None


def colorize(line: str, grep: Optional["re.Pattern[str]"] = None) -> str:
    if not colors.enabled:
        return line

    prefix = ""
    m = _COMPOSE_PREFIX_RE.match(line)
    if m:
        prefix = m.group(1)
        line = line[len(prefix):]
        name = prefix.split()[0]
        prefix = paint(prefix, _PREFIX_COLORS[zlib.crc32(name.encode()) % len(_PREFIX_COLORS)])

    level = level_of(line)
    stamp = ""
    m = _LEADING_TIME_RE.match(line)
    if m:
        stamp, line = paint(m.group(1), DIM), line[m.end():]

    if grep:
        # Highlight matches, then restore the line's own color after each.
        base = {"error": RED, "warn": YELLOW, "debug": DIM}.get(level or "", "")
        line = grep.sub(lambda g: paint(g.group(0), REVERSE, BOLD) + base, line)

    if level == "error":
        line = paint(line, RED)
    elif level == "warn":
        line = paint(line, YELLOW)
    elif level == "debug":
        line = paint(line, DIM)
    elif level == "info":
        line = _LEVEL_RE.sub(lambda g: paint(g.group(0), GREEN), line, count=1)

    return prefix + stamp + line


def run(argv: Sequence[str], opts: Options) -> int:
    try:
        process = subprocess.Popen(
            list(argv),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # containers often log to stderr
            text=True,
            errors="replace",
            bufsize=1,
        )
    except FileNotFoundError:
        sys.stderr.write(f"{argv[0]}: command not found\n")
        return 127

    assert process.stdout is not None
    try:
        for raw in process.stdout:
            line = raw.rstrip("\n")
            if opts.grep and not opts.grep.search(line):
                continue
            sys.stdout.write(colorize(line, opts.grep) + "\n")
            sys.stdout.flush()
        return process.wait()
    except KeyboardInterrupt:
        process.terminate()
        return 130
    except BrokenPipeError:
        # `pprint docker logs web | head` closed the pipe early.
        process.terminate()
        return 0
