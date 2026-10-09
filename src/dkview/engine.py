from __future__ import annotations

import os
import shutil

ENGINES = ("docker", "podman")


def name() -> str:
    chosen = os.environ.get("DKVIEW_ENGINE", "").strip()
    if chosen:
        return chosen
    for engine in ENGINES:
        if shutil.which(engine):
            return engine
    return "docker"


def kind(program: str) -> str:
    base = program.replace("\\", "/").rsplit("/", 1)[-1].lower()
    for ext in (".exe", ".cmd", ".bat"):
        if base.endswith(ext):
            base = base[:-len(ext)]
    return base if base in ENGINES else ""


def is_podman(argv) -> bool:
    return bool(argv) and kind(argv[0]) == "podman"
