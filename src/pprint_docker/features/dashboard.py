"""`pprint dash`: containers, services, problems and disk use on one screen."""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from ..ansi import BOLD, DIM, GREEN, RED, YELLOW, paint, terminal_width
from ..layout import render
from ..options import Options
from ..runner import capture
from ..styles import container_status, replicas, styler
from ..table import Table
from ..transform import compact_age, short_image


def _json_lines(argv: List[str]) -> Optional[List[Dict[str, Any]]]:
    result = capture(argv)
    if result.code != 0:
        return None
    items = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line:
            try:
                items.append(json.loads(line))
            except ValueError:
                pass
    return items


def collect() -> Dict[str, Any]:
    """Ask docker for everything at once; `stats` alone takes ~2 seconds."""
    commands = {
        "info": ["docker", "info", "--format", "{{json .}}"],
        "ps": ["docker", "ps", "-a", "--format", "{{json .}}"],
        "stats": ["docker", "stats", "--no-stream", "--format", "{{json .}}"],
        "services": ["docker", "service", "ls", "--format", "{{json .}}"],
        "df": ["docker", "system", "df", "--format", "{{json .}}"],
    }
    with ThreadPoolExecutor(len(commands)) as pool:
        futures = {k: pool.submit(_json_lines, v) for k, v in commands.items()}
        return {k: f.result() for k, f in futures.items()}


def _header(info: Dict[str, Any]) -> str:
    swarm = (info.get("Swarm") or {}).get("LocalNodeState", "")
    mem = info.get("MemTotal") or 0
    parts = [
        f"Docker {info.get('ServerVersion', '?')} on {info.get('Name', '?')}",
        f"{info.get('NCPU', '?')} CPUs",
        f"{mem / 1024 ** 3:.1f}GiB RAM" if mem else "",
        f"swarm {swarm}" if swarm and swarm != "inactive" else "",
    ]
    return paint(" · ".join(p for p in parts if p), BOLD)


def _counts(ps: List[Dict[str, Any]]) -> str:
    running = sum(1 for c in ps if c.get("State") == "running")
    unhealthy = sum(1 for c in ps if "unhealthy" in c.get("Status", ""))
    failed = sum(1 for c in ps if c.get("State") == "exited"
                 and not c.get("Status", "").startswith("Exited (0)"))
    stopped = sum(1 for c in ps if c.get("State") != "running") - failed
    pieces = [paint(f"{running} running", GREEN)]
    if unhealthy:
        pieces.append(paint(f"{unhealthy} unhealthy", RED))
    if failed:
        pieces.append(paint(f"{failed} failed", RED))
    if stopped:
        pieces.append(paint(f"{stopped} stopped", DIM))
    return "Containers: " + " · ".join(pieces)


def _problems(ps: List[Dict[str, Any]], services: List[Dict[str, Any]]) -> List[str]:
    problems = []
    for c in ps:
        status = c.get("Status", "")
        if container_status(status) == RED:
            problems.append(f"container {c.get('Names')}: {compact_age(status)}")
        elif c.get("State") == "restarting":
            problems.append(f"container {c.get('Names')}: restarting")
    for s in services:
        if replicas(s.get("Replicas", "")) in (RED, YELLOW):
            problems.append(f"service {s.get('Name')}: {s.get('Replicas')} replicas running")
    return problems


def frame(opts: Options, width: Optional[int] = None) -> str:
    width = width or opts.width or terminal_width()
    data = collect()
    if data["ps"] is None:
        return paint("Cannot reach the docker daemon. Is it running?", RED) + "\n"

    info = (data["info"] or [{}])[0]
    ps = data["ps"]
    stats = {s.get("ID", "")[:12]: s for s in data["stats"] or []}
    services = data["services"] or []

    out = [_header(info), _counts(ps), ""]

    problems = _problems(ps, services)
    if problems:
        out.append(paint(f"Needs attention ({len(problems)})", BOLD, RED))
        out += ["  " + paint("✗ ", RED) + p for p in problems]
    else:
        out.append(paint("✓ Everything is running and healthy", GREEN))
    out.append("")

    def order(c: Dict[str, Any]) -> tuple:
        bad = container_status(c.get("Status", "")) == RED
        return (not bad, c.get("State") != "running", c.get("Names", ""))

    containers = Table(["NAME", "STATUS", "IMAGE", "CPU %", "MEM", "PORTS"])
    for c in sorted(ps, key=order):
        s = stats.get(c.get("ID", "")[:12], {})
        mem = s.get("MemUsage", "").split(" / ")[0]
        ports = re.sub(r"(0\.0\.0\.0|\[::\]|:::)", "", c.get("Ports", ""))
        ports = ", ".join(dict.fromkeys(p.strip() for p in ports.split(",") if p.strip()))
        image = c.get("Image", "")
        containers.rows.append([
            c.get("Names", ""), compact_age(c.get("Status", "")),
            short_image(image) if opts.short else image,
            s.get("CPUPerc", ""), mem, ports,
        ])
    out.append(paint("Containers", BOLD))
    out.append(render(containers, width, styler))

    if services:
        table = Table(["NAME", "MODE", "REPLICAS", "IMAGE", "PORTS"])
        for s in sorted(services, key=lambda s: s.get("Name", "")):
            image = re.sub(r"@sha256:[0-9a-f]+", "", s.get("Image", ""))
            table.rows.append([s.get("Name", ""), s.get("Mode", ""), s.get("Replicas", ""),
                               short_image(image) if opts.short else image, s.get("Ports", "")])
        out += ["", paint("Services", BOLD), render(table, width, styler)]

    if data["df"]:
        table = Table(["TYPE", "TOTAL", "ACTIVE", "SIZE", "RECLAIMABLE"])
        for d in data["df"]:
            table.rows.append([d.get("Type", ""), str(d.get("TotalCount", "")),
                               str(d.get("Active", "")), d.get("Size", ""),
                               d.get("Reclaimable", "")])
        out += ["", paint("Disk", BOLD), render(table, width, styler)]

    return "\n".join(out) + "\n"
