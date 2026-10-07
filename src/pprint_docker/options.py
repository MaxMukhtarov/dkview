"""Settings shared by every feature, filled in from the command line."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Options:
    width: Optional[int] = None
    cols: List[str] = field(default_factory=list)
    sort: Optional[str] = None
    desc: bool = False
    grep: Optional["re.Pattern[str]"] = None
    short: bool = False
    humanize: bool = True
    trunc: bool = False
    watch: bool = False
    once: bool = False
    interval: float = 2.0
    full: bool = False
    group: bool = False
    keep: int = 3
    dry_run: bool = False
    yes: bool = False
