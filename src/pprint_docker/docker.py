"""Understanding docker command lines: which subcommand, and how to run it."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Sequence

# Options that take a separate value (`--context prod`, `-f file.yml`,
# `--filter status=exited`). The value is skipped when looking for the
# subcommand words.
VALUE_OPTIONS = {
    "-c", "--context", "-H", "--host", "--config", "-l", "--log-level",
    "--tlscacert", "--tlscert", "--tlskey",
    "-f", "--file", "--filter", "-p", "--project-name",
    "--project-directory", "--env-file", "--profile",
    "-n", "--tail", "--since", "--until",
}

LIST_VERBS = {"ls", "list"}

# Commands whose output is a table. Anything not listed here (run, exec,
# build, events, typos, --help...) runs straight through untouched.
TABLE_COMMANDS = {
    "ps": None, "images": None, "stats": None, "top": None,
    "history": None, "search": None,
    "container": LIST_VERBS | {"ps", "stats", "top"},
    "image": LIST_VERBS | {"history"},
    "volume": LIST_VERBS,
    "network": LIST_VERBS,
    "service": LIST_VERBS | {"ps"},
    "node": LIST_VERBS | {"ps"},
    "stack": LIST_VERBS | {"ps", "services"},
    "secret": LIST_VERBS,
    "config": LIST_VERBS,
    "context": LIST_VERBS,
    "plugin": LIST_VERBS,
    "system": {"df"},
    "compose": {"ps", "ls", "images", "top", "stats"},
    "buildx": LIST_VERBS,
}

INSPECT_OBJECTS = {"container", "image", "service", "network", "volume",
                   "node", "secret", "config", "plugin", "context"}

LOG_OBJECTS = {"container", "service", "compose"}

# Every top-level docker command, so `pprint ps` can mean `docker ps`.
DOCKER_COMMANDS = {
    "attach", "build", "builder", "buildx", "commit", "compose", "config",
    "container", "context", "cp", "create", "diff", "events", "exec",
    "export", "history", "image", "images", "import", "info", "inspect",
    "kill", "load", "login", "logout", "logs", "manifest", "network",
    "node", "pause", "plugin", "port", "ps", "pull", "push", "rename",
    "restart", "rm", "rmi", "run", "save", "search", "secret", "service",
    "stack", "start", "stats", "stop", "swarm", "system", "tag", "top",
    "trust", "unpause", "update", "version", "volume", "wait",
}


def is_docker(argv: Sequence[str]) -> bool:
    return bool(argv) and os.path.basename(argv[0]) in {"docker", "docker.exe"}


def expand_shortcut(argv: List[str]) -> List[str]:
    """`pprint ps -a` -> `docker ps -a`."""
    if argv and argv[0] in DOCKER_COMMANDS:
        return ["docker"] + argv
    return argv


def words(argv: Sequence[str], limit: int = 2) -> List[str]:
    """First non-option words after `docker`.

    `docker --context prod service ls -q` -> ['service', 'ls']
    """
    found: List[str] = []
    skip = False
    for arg in argv[1:]:
        if skip:
            skip = False
        elif arg in VALUE_OPTIONS:
            skip = True
        elif not arg.startswith("-"):
            found.append(arg)
            if len(found) == limit:
                break
    return found


def has_option(argv: Sequence[str], *names: str) -> bool:
    return any(a in names or any(a.startswith(n + "=") for n in names
                                 if n.startswith("--"))
               for a in argv)


def user_chose_format(argv: Sequence[str]) -> bool:
    return has_option(argv, "--format", "-q", "--quiet", "--pretty")


@dataclass
class Kind:
    """What pprint should do with a docker command."""

    name: str  # "table", "stats", "logs", "inspect" or "passthrough"


def classify(argv: Sequence[str]) -> Kind:
    w = words(argv)
    if not w or has_option(argv, "-h", "--help"):
        return Kind("passthrough")

    first = w[0]
    second = w[1] if len(w) > 1 else None

    if first == "logs" or (first in LOG_OBJECTS and second == "logs"):
        return Kind("logs")

    if first == "inspect" or (first in INSPECT_OBJECTS and second == "inspect"):
        if user_chose_format(argv):
            return Kind("passthrough")
        return Kind("inspect")

    if user_chose_format(argv) and not _is_table_format(argv):
        return Kind("passthrough")

    if first not in TABLE_COMMANDS:
        return Kind("passthrough")
    verbs = TABLE_COMMANDS[first]
    if verbs is not None and second not in verbs:
        return Kind("passthrough")

    # Layouts that are not a single table.
    if [first, second] == ["system", "df"] and has_option(argv, "-v", "--verbose"):
        return Kind("passthrough")
    if has_option(argv, "--tree"):
        return Kind("passthrough")

    if first == "stats" or (first in ("container", "compose") and second == "stats"):
        return Kind("stats")
    return Kind("table")


def _is_table_format(argv: Sequence[str]) -> bool:
    """`--format 'table {{.Names}}\t{{.Status}}'` still prints a table."""
    for i, arg in enumerate(argv):
        value = None
        if arg == "--format" and i + 1 < len(argv):
            value = argv[i + 1]
        elif arg.startswith("--format="):
            value = arg.split("=", 1)[1]
        if value is not None:
            return value.strip().startswith("table")
    return False


# Commands that accept --no-trunc. pprint asks for full values and wraps
# them itself, then shortens IDs back to docker's usual 12 characters.
NO_TRUNC = {
    ("ps",), ("images",), ("history",), ("search",),
    ("container", "ls"), ("container", "ps"), ("container", "list"),
    ("image", "ls"), ("image", "list"), ("image", "history"),
    ("service", "ps"), ("stack", "ps"), ("node", "ps"),
    ("network", "ls"), ("network", "list"), ("compose", "ps"),
}


def supports_no_trunc(argv: Sequence[str]) -> bool:
    w = words(argv)
    return tuple(w[:1]) in NO_TRUNC or tuple(w[:2]) in NO_TRUNC


def prepare(argv: Sequence[str], trunc: bool) -> List[str]:
    """Flags that make docker print one complete snapshot we can format."""
    argv = list(argv)
    kind = classify(argv)

    # `docker stats` refreshes forever by default; take a single sample.
    if kind.name == "stats" and "--no-stream" not in argv:
        argv.append("--no-stream")

    # Full values so COMMAND or ERROR are not cut short; pprint wraps
    # long values itself.
    if (kind.name == "table" and supports_no_trunc(argv) and not trunc
            and not has_option(argv, "--no-trunc", "--format", "-q", "--quiet")):
        argv.append("--no-trunc")

    return argv
