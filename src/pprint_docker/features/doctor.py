"""`pprint doctor`: what is wrong with each swarm service, and why."""

from __future__ import annotations

import json
import re
import sys
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

from ..ansi import BOLD, DIM, GREEN, RED, YELLOW, paint, terminal_width
from ..layout import render
from ..options import Options
from ..runner import capture
from ..styles import styler
from ..table import Table
from ..transform import compact_age, short_image, sort_key
from .images import global_options

OK, WARN, BAD = "ok", "warn", "bad"
FAILED_STATES = ("failed", "rejected", "orphaned")


@dataclass
class Task:
    slot: str
    node: str
    desired: str
    state: str      # "Failed"
    when: str       # "4s ago"
    error: str

    @classmethod
    def from_json(cls, item: dict) -> "Task":
        current = item.get("CurrentState", "")
        state, _, when = current.partition(" ")
        return cls(
            slot=item.get("Name", ""),
            node=item.get("Node", ""),
            desired=item.get("DesiredState", ""),
            state=state,
            when=compact_age(when),
            error=item.get("Error", "").strip().strip('"').strip(),
        )

    @property
    def failed(self) -> bool:
        return self.state.lower() in FAILED_STATES


@dataclass
class ServiceReport:
    name: str
    replicas: str
    image: str
    tasks: List[Task] = field(default_factory=list)
    update_state: str = ""
    update_message: str = ""

    @property
    def running(self) -> int:
        m = re.match(r"(\d+)/(\d+)", self.replicas)
        return int(m.group(1)) if m else 0

    @property
    def wanted(self) -> int:
        m = re.match(r"(\d+)/(\d+)", self.replicas)
        return int(m.group(2)) if m else 0

    @property
    def failures(self) -> List[Task]:
        return [t for t in self.tasks if t.failed]

    @property
    def health(self) -> str:
        if self.running < self.wanted:
            return BAD
        if self.failures or self.update_state in ("paused", "rollback_started",
                                                  "rollback_paused"):
            return WARN
        return OK


def _json_lines(text: str) -> List[dict]:
    items = []
    for line in text.splitlines():
        try:
            items.append(json.loads(line))
        except ValueError:
            pass
    return items


def collect(argv: Sequence[str]) -> Optional[List[ServiceReport]]:
    base = global_options(argv)
    listing = capture(base + ["service", "ls", "--format", "{{json .}}"])
    if listing.code != 0:
        message = listing.stderr.strip()
        if "not a swarm manager" in message or "swarm" in message.lower():
            sys.stderr.write("pprint doctor: this node is not a swarm manager, "
                             "so there are no services to check.\n")
        else:
            sys.stderr.write(listing.stderr)
        return None

    services = [ServiceReport(s.get("Name", ""), s.get("Replicas", ""),
                              re.sub(r"@sha256:[0-9a-f]+", "", s.get("Image", "")))
                for s in _json_lines(listing.stdout)]
    if not services:
        return []

    def tasks_of(name: str) -> List[Task]:
        result = capture(base + ["service", "ps", name, "--no-trunc", "--format", "{{json .}}"])
        return [Task.from_json(t) for t in _json_lines(result.stdout)]

    with ThreadPoolExecutor(min(8, len(services))) as pool:
        for service, tasks in zip(services, pool.map(tasks_of, [s.name for s in services])):
            service.tasks = tasks

    inspect = capture(base + ["service", "inspect", "--format", "{{json .}}"]
                      + [s.name for s in services])
    for service, data in zip(services, _json_lines(inspect.stdout)):
        status = data.get("UpdateStatus") or {}
        service.update_state = status.get("State", "") or ""
        service.update_message = status.get("Message", "") or ""
    return services


# ------------------------------------------------------------------ hints

_HINTS = [
    (r"failed to resolve reference|no such image|manifest unknown|not found: manifest|"
     r"pull access denied|unauthorized",
     "The image can't be pulled. Check the image name and tag, and that the "
     "node can log in to the registry (deploy with --with-registry-auth)."),
    (r"non-zero exit \(137\)",
     "The container was killed (exit 137): usually out of memory or a failed "
     "health check. Check memory limits and `pprint errors {name}`."),
    (r"non-zero exit \((\d+)\)",
     "The program inside the container exited with an error. "
     "See why with `pprint errors {name}`."),
    (r"no suitable node",
     "No node matches the service's placement constraints or resources. "
     "Check constraints, labels and reserved CPU/memory."),
    (r"port .* is already in use|address already in use",
     "A published port is already taken on the node."),
    (r"invalid mount|bind source path does not exist|no such file or directory",
     "A volume or bind mount source doesn't exist on the node."),
    (r"unhealthy container|health check",
     "The container's health check keeps failing. "
     "Check `pprint inspect` on a task container and the service logs."),
]


def hint(error: str, service: str) -> str:
    for pattern, text in _HINTS:
        if re.search(pattern, error, re.IGNORECASE):
            return text.format(name=service)
    return ""


# -------------------------------------------------------------- rendering

def error_table(report: ServiceReport, every_task: bool) -> Table:
    if every_task:
        table = Table(["TASK", "NODE", "STATE", "WHEN", "ERROR"])
        for t in report.failures:
            table.rows.append([t.slot, t.node, t.state, t.when, t.error])
        return table

    groups: "OrderedDict[str, List[Task]]" = OrderedDict()
    for t in report.failures:
        groups.setdefault(t.error or "(no error message)", []).append(t)
    table = Table(["TIMES", "STATE", "LAST", "NODES", "ERROR"])
    for error, tasks in groups.items():
        latest = min(tasks, key=lambda t: sort_key(t.when))
        states = ", ".join(OrderedDict.fromkeys(t.state for t in tasks))
        nodes = ", ".join(OrderedDict.fromkeys(t.node for t in tasks if t.node))
        table.rows.append([f"{len(tasks)}×", states, latest.when, nodes, error])
    return table


def _current(report: ServiceReport) -> str:
    latest: Dict[str, Task] = OrderedDict()
    for t in report.tasks:  # docker lists the newest task of each slot first
        latest.setdefault(t.slot, t)
    states = [f"{t.state} {t.when}".strip() for t in latest.values()
              if t.desired.lower() != "shutdown" or t.failed]
    return "; ".join(OrderedDict.fromkeys(states))


def render_report(services: List[ServiceReport], opts: Options) -> str:
    out: List[str] = []
    counts = {h: sum(1 for s in services if s.health == h) for h in (OK, WARN, BAD)}
    pieces = [paint(f"{counts[OK]} healthy", GREEN)]
    if counts[WARN]:
        pieces.append(paint(f"{counts[WARN]} restarting", YELLOW))
    if counts[BAD]:
        pieces.append(paint(f"{counts[BAD]} failing", RED))
    out.append(paint("Swarm services: ", BOLD) + " · ".join(pieces))
    out.append("")

    order = {BAD: 0, WARN: 1, OK: 2}
    problems = sorted((s for s in services if s.health != OK),
                      key=lambda s: (order[s.health], s.name))
    for s in problems:
        icon, color = ("✗", RED) if s.health == BAD else ("!", YELLOW)
        image = short_image(s.image) if opts.short else s.image
        out.append(paint(f"{icon} {s.name}", BOLD, color) + "  "
                   + paint(f"{s.replicas} replicas", color) + paint(f" · {image}", DIM))
        restarts = len(s.failures)
        details = [f"{restarts} failed tasks in recent history" if restarts else ""]
        current = _current(s)
        if current:
            details.append(f"now: {current}")
        if s.update_state:
            details.append(f"update {s.update_state}"
                           + (f": {s.update_message}" if s.update_message else ""))
        out.append("  " + " · ".join(d for d in details if d))
        if s.failures:
            table = error_table(s, opts.full)
            out += ["  " + line for line in render(table, (opts.width or terminal_width()) - 2, styler).splitlines()]
            seen = set()
            for row in table.rows:
                text = hint(row[-1], s.name)
                if text and text not in seen:
                    seen.add(text)
                    out.append("  " + paint("→ ", YELLOW) + text)
        out.append("")

    healthy = [s for s in services if s.health == OK]
    if healthy:
        table = Table(["SERVICE", "REPLICAS", "IMAGE"])
        for s in sorted(healthy, key=lambda s: s.name):
            table.rows.append([s.name, s.replicas, short_image(s.image) if opts.short else s.image])
        out.append(paint("✓ Healthy", BOLD, GREEN))
        out.append(render(table, opts.width or terminal_width(), styler))
    elif not problems:
        out.append("No services.")
    return "\n".join(out).rstrip("\n") + "\n"


def run(argv: Sequence[str], opts: Options) -> int:
    services = collect(argv)
    if services is None:
        return 1
    if opts.grep:
        services = [s for s in services if opts.grep.search(s.name)]
    sys.stdout.write(render_report(services, opts))
    if opts.full is False and any(s.failures for s in services):
        sys.stdout.write(paint("(identical errors are grouped; --full lists every task)\n", DIM))
    return 1 if any(s.health == BAD for s in services) else 0
