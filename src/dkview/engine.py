"""Which container engine to run: docker, or podman where docker is missing.

DKVIEW_ENGINE=podman (or a full path) picks one explicitly.
"""

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
    return "docker"   # not installed: let docker's own "not found" error show


def kind(program: str) -> str:
    """'docker', 'podman' or '' for /usr/bin/podman, docker.exe, ..."""
    base = program.replace("\\", "/").rsplit("/", 1)[-1].lower()
    for ext in (".exe", ".cmd", ".bat"):
        if base.endswith(ext):
            base = base[:-len(ext)]
    return base if base in ENGINES else ""


def is_podman(argv) -> bool:
    return bool(argv) and kind(argv[0]) == "podman"
