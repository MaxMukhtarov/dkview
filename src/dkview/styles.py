from __future__ import annotations

import re
from typing import Optional

from .ansi import BOLD, CYAN, DIM, GREEN, RED, YELLOW

GOOD, WARN, BAD, MUTED = GREEN, YELLOW, RED, DIM


def container_status(value: str) -> Optional[str]:
    v = value.lower()
    if v.startswith("up"):
        if "unhealthy" in v:
            return BAD
        if "health: starting" in v or "paused" in v:
            return WARN
        return GOOD
    if v.startswith("exited"):
        return MUTED if re.match(r"exited \(0\)", v) else BAD
    if v.startswith(("restarting", "removal")):
        return WARN
    if v.startswith("dead"):
        return BAD
    if v.startswith("created"):
        return MUTED
    return None


def state_word(value: str) -> Optional[str]:
    v = value.lower().split(" ")[0] if value else ""
    if v in ("running", "ready", "active", "complete", "healthy", "leader", "reachable"):
        return GOOD if v != "complete" else MUTED
    if v in ("failed", "rejected", "down", "dead", "unhealthy", "unreachable",
             "orphaned", "disconnected", "unknown"):
        return BAD
    if v in ("pending", "preparing", "starting", "assigned", "accepted",
             "new", "allocated", "restarting", "paused", "pause", "drain",
             "created", "remove"):
        return WARN
    if v in ("shutdown", "exited", "removing"):
        return MUTED
    return None


def replicas(value: str) -> Optional[str]:
    m = re.match(r"^(\d+)/(\d+)", value)
    if not m:
        return None
    running, wanted = int(m.group(1)), int(m.group(2))
    if running >= wanted:
        return GOOD
    return BAD if running == 0 else WARN


def percent(value: str) -> Optional[str]:
    m = re.match(r"^(\d+(?:\.\d+)?)%", value)
    if not m:
        return None
    number = float(m.group(1))
    if number >= 80:
        return BAD
    if number >= 50:
        return WARN
    return None


def styler(header: str, value: str) -> Optional[str]:
    if not value:
        return None
    h = header.upper()

    if h == "STATUS":
        return container_status(value) or state_word(value)
    if h in ("STATE", "CURRENT STATE", "AVAILABILITY", "HEALTH"):
        return state_word(value)
    if h == "MANAGER STATUS":
        return CYAN + BOLD if value.lower() == "leader" else state_word(value)
    if h == "REPLICAS":
        return replicas(value)
    if h in ("CPU %", "MEM %", "CPU", "MEM"):
        return percent(value)
    if h == "ERROR":
        return BAD
    if h in ("NAME", "NAMES", "SERVICE"):
        return BOLD
    return None
