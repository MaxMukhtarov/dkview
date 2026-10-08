"""`dkview errors`: errors and warnings from logs, counted and grouped.

    dkview errors                      every service and container on the host
    dkview errors orders --since 2d one stack, a service or a container
"""

from __future__ import annotations

import json
import queue
import re
import subprocess
import sys
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence, Tuple

from ..ansi import BOLD, DIM, GREEN, RED, YELLOW, paint, terminal_width
from ..formats import fields_template
from ..layout import render, wrap_cell
from ..options import Options
from ..runner import capture
from ..table import Table
from ..units import ago
from .images import global_options
from .logs import level_of

DEFAULT_SINCE = "30m"
TOP = 10  # message groups shown per source unless --full

# ------------------------------------------------------------------ time

_DURATION_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(w|d|h|m|s)", re.IGNORECASE)
_DURATION_UNITS = {"w": 604800, "d": 86400, "h": 3600, "m": 60, "s": 1}


def parse_since(text: str) -> Optional[float]:
    """'30m' -> 1800.0, '2d' -> 172800.0, '1h30m' -> 5400.0; else None.

    docker only understands s/m/h, so days and weeks are converted here.
    """
    compact = text.replace(" ", "")
    if not compact or _DURATION_RE.sub("", compact):
        return None
    return sum(float(n) * _DURATION_UNITS[u.lower()]
               for n, u in _DURATION_RE.findall(compact))


def since_for_docker(text: str) -> str:
    """'2d' -> '172800s'; timestamps and anything else are passed through."""
    seconds = parse_since(text)
    return f"{int(seconds)}s" if seconds is not None else text


def window_label(text: str) -> str:
    return f"last {text}" if parse_since(text) is not None else f"since {text}"


_STAMP_RE = re.compile(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.\d+)?(Z|[+-]\d\d:\d\d)? ?")


def split_stamp(line: str) -> Tuple[Optional[datetime], str]:
    """Separate the timestamp `--timestamps` puts in front of each line."""
    m = _STAMP_RE.match(line)
    if not m:
        return None, line
    zone = m.group(2) or "Z"
    zone = "+00:00" if zone == "Z" else zone
    try:
        when = datetime.fromisoformat(m.group(1) + zone)
    except ValueError:
        return None, line
    return when, line[m.end():]


# ------------------------------------------------------------- messages

# Lines with no level word that still clearly report a failure.
_IMPLICIT_ERROR_RE = re.compile(
    r"\b[A-Z][\w.]*(?:Exception|Error)\b|^Traceback \(most recent call last\)|^panic: ")

# A timestamp or level an app writes at the start of its own lines.
_APP_PREFIX_RE = re.compile(
    r"^\s*(?:\[?\d{4}-\d\d-\d\d[T ][\d:.,]+(?:Z|[+-]\d\d:?\d\d)?\]?\s*)+")

_VARIABLE_PARTS = [
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I), "<id>"),
    (re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?\b"), "<ip>"),
    (re.compile(r"\b(?=[0-9a-f]*\d)[0-9a-f]{6,}\b", re.I), "#"),
    (re.compile(r"\b\d{4}-\d\d-\d\d[T ][\d:.,]+(?:Z|[+-]\d\d:?\d\d)?"), "<time>"),
    (re.compile(r"\w*\d[\w.]*"), "#"),  # any word with a digit in it
]


def level(message: str) -> Optional[str]:
    found = level_of(message)
    if found in ("error", "warn"):
        return found
    if found is None and _IMPLICIT_ERROR_RE.search(message):
        return "error"
    return None


def clean_message(message: str) -> str:
    return " ".join(_APP_PREFIX_RE.sub("", message).split())


def signature(message: str) -> str:
    """What stays the same between repeats: numbers, ids and IPs removed."""
    text = clean_message(message)
    for pattern, placeholder in _VARIABLE_PARTS:
        text = pattern.sub(placeholder, text)
    return text.lower()


@dataclass
class Group:
    level: str
    message: str            # the most recent example
    count: int = 0
    first: Optional[datetime] = None
    last: Optional[datetime] = None


@dataclass
class Source:
    name: str
    kind: str               # "service" or "container"
    command: List[str]
    groups: Dict[str, Group] = field(default_factory=dict)
    lines: int = 0
    problem: str = ""       # docker's own complaint, if the logs couldn't be read

    def count(self, which: str) -> int:
        return sum(g.count for g in self.groups.values() if g.level == which)

    @property
    def errors(self) -> int:
        return self.count("error")

    @property
    def warnings(self) -> int:
        return self.count("warn")

    @property
    def last_error(self) -> Optional[datetime]:
        times = [g.last for g in self.groups.values() if g.level == "error" and g.last]
        return max(times) if times else None

    def add(self, line: str, grep: Optional["re.Pattern[str]"] = None) -> None:
        when, message = split_stamp(line)
        if when is None:
            # Every real log line has a timestamp; this one is from docker.
            if line.strip():
                self.problem = (self.problem + " " + line.strip()).strip()
            return
        self.lines += 1
        found = level(message)
        if not found or (grep and not grep.search(message)):
            return
        key = signature(message)
        group = self.groups.get(key)
        if group is None:
            group = self.groups[key] = Group(found, clean_message(message), first=when)
        group.count += 1
        if group.last is None or when >= group.last:
            group.last, group.message = when, clean_message(message)
        if group.first is None or when < group.first:
            group.first = when


# `docker service logs` sometimes prints everything and then never exits
# (a swarm bug with tasks whose containers are gone). When no line has
# arrived for this long, what came so far is counted and docker is stopped.
# The first line may take longer: docker reads old log files to find --since.
IDLE_SECONDS = 8.0
FIRST_LINE_SECONDS = 30.0


def read(source: Source, grep: Optional["re.Pattern[str]"] = None,
         idle: float = IDLE_SECONDS, first: float = FIRST_LINE_SECONDS) -> Source:
    """Stream the logs (they can be large) and count them line by line."""
    try:
        process = subprocess.Popen(
            source.command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # apps log to stderr too
            text=True, encoding="utf-8", errors="replace")
    except FileNotFoundError:
        source.problem = f"{source.command[0]}: command not found"
        return source
    assert process.stdout is not None

    lines: "queue.Queue[Optional[str]]" = queue.Queue(maxsize=10000)

    def pump() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            lines.put(line)
        lines.put(None)

    threading.Thread(target=pump, daemon=True).start()
    wait = first
    while True:
        try:
            line = lines.get(timeout=wait)
        except queue.Empty:
            process.kill()
            source.problem = (f"docker stopped sending logs for {wait:.0f}s without "
                              "finishing; counted what had arrived")
            break
        wait = idle
        if line is None:
            break
        source.add(line.rstrip("\n"), grep)
    process.wait()
    return source


# ------------------------------------------------------------ resolving

def _json_lines(text: str) -> List[dict]:
    items = []
    for line in text.splitlines():
        try:
            items.append(json.loads(line))
        except ValueError:
            pass
    return items


def _labels(text: object) -> Dict[str, str]:
    """docker gives "a=1,b=2"; podman gives {"a": "1"} or null."""
    if isinstance(text, dict):
        return {str(k): str(v) for k, v in text.items()}
    pairs = (item.partition("=") for item in str(text or "").split(","))
    return {key: value for key, _, value in pairs if key}


@dataclass
class Host:
    stacks: List[str]
    services: List[dict]     # {"Name", "ID"}
    containers: List[dict]   # {"Names", "ID", "Labels", ...}

    @classmethod
    def load(cls, base: List[str]) -> "Host":
        services = capture(base + ["service", "ls", "--format", "{{json .}}"])
        stacks = capture(base + ["stack", "ls", "--format", "{{.Name}}"]) \
            if services.code == 0 else None
        containers = capture(base + ["ps", "-a", "--no-trunc", "--format",
                                     fields_template(["ID", "Names", "Labels"])])
        return cls(
            stacks=stacks.stdout.split() if stacks and stacks.code == 0 else [],
            services=_json_lines(services.stdout) if services.code == 0 else [],
            containers=_json_lines(containers.stdout),
        )

    @property
    def swarm(self) -> bool:
        return bool(self.services)


def _service_source(base: List[str], name: str, since: str) -> Source:
    return Source(name, "service", base + [
        "service", "logs", "--raw", "--timestamps", "--since", since, name])


def _container_source(base: List[str], name: str, since: str) -> Source:
    return Source(name, "container", base + [
        "logs", "--timestamps", "--since", since, name])


def _by_name_or_id(items: List[dict], target: str, name_key: str) -> List[dict]:
    exact = [i for i in items if i.get(name_key) == target or i.get("ID") == target
             or (len(target) > 12 and target.startswith(i.get("ID") or "-"))]
    if exact:
        return exact[:1]
    return [i for i in items if i.get("ID", "").startswith(target)] if len(target) >= 3 else []


def resolve(host: Host, base: List[str], targets: Sequence[str],
            since: str) -> Tuple[List[Source], List[str]]:
    """Turn names or IDs into log sources; also return the ones not found.

    A stack becomes all of its services, then services, then containers.
    """
    sources: "OrderedDict[Tuple[str, str], Source]" = OrderedDict()
    missing: List[str] = []

    def add(source: Source) -> None:
        sources.setdefault((source.kind, source.name), source)

    for target in targets:
        if target in host.stacks:
            prefix = target + "_"
            for s in host.services:
                if s.get("Name", "").startswith(prefix):
                    add(_service_source(base, s["Name"], since))
            continue
        services = _by_name_or_id(host.services, target, "Name")
        if services:
            add(_service_source(base, services[0]["Name"], since))
            continue
        containers = _by_name_or_id(host.containers, target, "Names")
        if len(containers) == 1:
            add(_container_source(base, containers[0]["Names"], since))
        elif containers:
            missing.append(f"{target} (matches {len(containers)} containers, give more of the ID)")
        else:
            missing.append(target)
    return list(sources.values()), missing


def everything(host: Host, base: List[str], since: str) -> List[Source]:
    """Every service, plus the containers that aren't part of one.

    Swarm task containers are skipped when their service is covered, so the
    same lines aren't counted twice.
    """
    sources = [_service_source(base, s["Name"], since) for s in host.services]
    for c in host.containers:
        if host.swarm and "com.docker.swarm.service.name" in _labels(c.get("Labels", "")):
            continue
        sources.append(_container_source(base, c.get("Names", ""), since))
    return sources


# ------------------------------------------------------------- rendering

def plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _styler(header: str, value: str) -> Optional[str]:
    if header == "LEVEL":
        return RED if value == "error" else YELLOW
    if header == "ERRORS" and value not in ("", "0"):
        return RED
    if header == "WARNINGS" and value not in ("", "0"):
        return YELLOW
    if header in ("COUNT",):
        return BOLD
    if header == "SOURCE":
        return BOLD
    if header in ("LAST", "FIRST", "LAST ERROR", "KIND"):
        return DIM
    return None


def _order(source: Source) -> tuple:
    return (-source.errors, -source.warnings, source.name)


def summary_table(sources: List[Source], now: datetime) -> Table:
    table = Table(["SOURCE", "KIND", "ERRORS", "WARNINGS", "LAST ERROR", "LINES"])
    for s in sorted(sources, key=_order):
        table.rows.append([s.name, s.kind, str(s.errors), str(s.warnings),
                           ago(s.last_error, now), str(s.lines)])
    return table


def groups_table(source: Source, now: datetime, limit: Optional[int]) -> Table:
    table = Table(["COUNT", "LEVEL", "LAST", "FIRST", "MESSAGE"])
    groups = sorted(source.groups.values(),
                    key=lambda g: (g.level != "error", -g.count, g.message))
    for g in groups[:limit] if limit else groups:
        table.rows.append([f"{g.count}×", g.level, ago(g.last, now),
                           ago(g.first, now), g.message])
    return table


def render_report(sources: List[Source], opts: Options, since: str,
                  now: Optional[datetime] = None) -> str:
    now = now or datetime.now(timezone.utc)
    width = opts.width or terminal_width()
    out: List[str] = []

    errors = sum(s.errors for s in sources)
    warnings = sum(s.warnings for s in sources)
    noisy = [s for s in sources if s.groups]
    title = f"Errors and warnings, {window_label(since)}: "
    if errors or warnings:
        counts = []
        if errors:
            counts.append(paint(plural(errors, "error"), RED))
        if warnings:
            counts.append(paint(plural(warnings, "warning"), YELLOW))
        out.append(paint(title, BOLD) + " · ".join(counts)
                   + (f" in {plural(len(sources), 'source')}" if len(noisy) == len(sources)
                      else f" in {len(noisy)} of {plural(len(sources), 'source')}"))
    else:
        out.append(paint(title, BOLD) + paint("none", GREEN)
                   + f" in {plural(len(sources), 'source')}")

    if len(noisy) > 1:
        out.append(render(summary_table(noisy, now), width, _styler))
    quiet = sorted(s.name for s in sources if not s.groups and not s.problem)
    if quiet and noisy:
        names = wrap_cell(", ".join(quiet), max(20, width - len("nothing in ") - 2))
        indent = " " * len("✓ nothing in ")
        out.append(paint("✓ nothing in ", GREEN)
                   + paint(("\n" + indent).join(names), DIM))
    out.append("")

    limit = None if opts.full else TOP
    for s in sorted(noisy, key=_order):
        icon, color = ("✗", RED) if s.errors else ("!", YELLOW)
        details = [plural(s.errors, "error") if s.errors else "",
                   plural(s.warnings, "warning") if s.warnings else "",
                   plural(len(s.groups), "different message")]
        out.append(paint(f"{icon} {s.name}", BOLD, color) + paint(f"  {s.kind} · ", DIM)
                   + " · ".join(d for d in details if d))
        out += ["  " + line for line in
                render(groups_table(s, now, limit), width - 2, _styler).splitlines()]
        hidden = len(s.groups) - TOP
        if limit and hidden > 0:
            out.append(paint(f"  … {hidden} more kinds of messages (--full shows all)", DIM))
        out.append("")

    for s in sources:
        if s.problem:
            out.append(paint(f"! {s.name}: ", YELLOW) + s.problem)
    return "\n".join(out).rstrip("\n") + "\n"


def run(argv: Sequence[str], targets: Sequence[str], opts: Options) -> int:
    base = global_options(argv)
    since = opts.since or DEFAULT_SINCE
    if parse_since(since) is None and not re.match(r"\d{4}-\d\d-\d\d", since):
        sys.stderr.write(f"dkview errors: --since {since}: use a duration like 30m, 6h, 2d "
                         "or 1w, or a date like 2026-10-07T09:00\n")
        return 2
    docker_since = since_for_docker(since)

    host = Host.load(base)
    if targets:
        sources, missing = resolve(host, base, targets, docker_since)
        for name in missing:
            sys.stderr.write(f"dkview errors: no stack, service or container called {name}\n")
        if missing and not sources:
            return 2
    else:
        sources = everything(host, base, docker_since)
    if not sources:
        sys.stdout.write("No services or containers to read logs from.\n")
        return 0

    with ThreadPoolExecutor(min(8, len(sources))) as pool:
        list(pool.map(lambda s: read(s, opts.grep), sources))

    sys.stdout.write(render_report(sources, opts, since))
    return 1 if any(s.errors for s in sources) else 0

