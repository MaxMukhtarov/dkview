from __future__ import annotations

import json
from typing import Dict, List, Optional, Sequence, Tuple

from . import docker
from .table import Table

Column = Tuple[str, str]

CONTAINERS: List[Column] = [
    ("CONTAINER ID", "ID"), ("IMAGE", "Image"), ("COMMAND", "Command"),
    ("CREATED", "RunningFor"), ("STATUS", "Status"), ("PORTS", "Ports"),
    ("NAMES", "Names"),
]
IMAGES: List[Column] = [
    ("REPOSITORY", "Repository"), ("TAG", "Tag"), ("IMAGE ID", "ID"),
    ("CREATED", "CreatedSince"), ("SIZE", "Size"),
]
SERVICES: List[Column] = [
    ("ID", "ID"), ("NAME", "Name"), ("MODE", "Mode"), ("REPLICAS", "Replicas"),
    ("IMAGE", "Image"), ("PORTS", "Ports"),
]
TASKS: List[Column] = [
    ("ID", "ID"), ("NAME", "Name"), ("IMAGE", "Image"), ("NODE", "Node"),
    ("DESIRED STATE", "DesiredState"), ("CURRENT STATE", "CurrentState"),
    ("ERROR", "Error"), ("PORTS", "Ports"),
]
NODES: List[Column] = [
    ("ID", "ID"), ("HOSTNAME", "Hostname"), ("STATUS", "Status"),
    ("AVAILABILITY", "Availability"), ("MANAGER STATUS", "ManagerStatus"),
    ("ENGINE VERSION", "EngineVersion"),
]
STATS: List[Column] = [
    ("CONTAINER ID", "ID"), ("NAME", "Name"), ("CPU %", "CPUPerc"),
    ("MEM USAGE / LIMIT", "MemUsage"), ("MEM %", "MemPerc"), ("NET I/O", "NetIO"),
    ("BLOCK I/O", "BlockIO"), ("PIDS", "PIDs"),
]

LAYOUTS: Dict[Tuple[str, ...], List[Column]] = {
    ("ps",): CONTAINERS, ("container", "ls"): CONTAINERS,
    ("container", "ps"): CONTAINERS, ("container", "list"): CONTAINERS,
    ("images",): IMAGES, ("image", "ls"): IMAGES, ("image", "list"): IMAGES,
    ("service", "ls"): SERVICES, ("service", "list"): SERVICES,
    ("service", "ps"): TASKS, ("stack", "ps"): TASKS, ("node", "ps"): TASKS,
    ("node", "ls"): NODES, ("node", "list"): NODES,
    ("stats",): STATS, ("container", "stats"): STATS,
}

def layout(argv: Sequence[str]) -> Optional[List[Column]]:
    if not docker.is_docker(argv) or docker.has_option(argv, "--format", "-q", "--quiet"):
        return None
    w = tuple(docker.words(argv))
    base = LAYOUTS.get(w[:1]) or LAYOUTS.get(w[:2])
    if base is None:
        return None
    columns = list(base)
    if base is CONTAINERS and docker.has_option(argv, "-s", "--size"):
        columns.append(("SIZE", "Size"))
    if base is IMAGES and docker.has_option(argv, "--digests"):
        columns.insert(2, ("DIGEST", "Digest"))
    return columns


def _fields(columns: List[Column]) -> List[str]:
    fields = [field for _, field in columns]
    if columns[:2] == NODES[:2]:
        fields.append("Self")
    return fields


def fields_template(fields: Sequence[str]) -> str:
    return "{" + ",".join(f'"{f}":{{{{json .{f}}}}}' for f in fields) + "}"


def template(columns: List[Column]) -> str:
    return fields_template(_fields(columns))


def format_args(columns: List[Column]) -> List[str]:
    return ["--format", template(columns)]


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def to_table(columns: List[Column], output: str) -> Optional[Table]:
    items = []
    for line in output.splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except ValueError:
            return None
        if not isinstance(item, dict):
            return None
        items.append(item)

    table = Table([header for header, _ in columns])
    previous_task = None
    for item in items:
        row = [_text(item.get(field)) for _, field in columns]
        if columns[:2] == NODES[:2] and item.get("Self") is True:
            row[0] += " *"
        if columns[:2] == TASKS[:2]:
            name = row[1]
            if name and name == previous_task:
                row[1] = "\\_ " + name
            previous_task = name
        table.rows.append(row)
    return table


def is_format_error(stderr: str) -> bool:
    text = stderr.lower()
    return "template" in text or "can't evaluate field" in text or "--format" in text
