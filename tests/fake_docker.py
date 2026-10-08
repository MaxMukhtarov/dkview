#!/usr/bin/env python3
"""Stand-in for the docker CLI, serving recorded output from tests/fixtures.

Every call's arguments are appended to $FAKE_DOCKER_LOG so tests can check
what dvt actually ran.
"""

import json
import os
import re
import sys
import time
from typing import Optional

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, "fixtures")


def fixture(name: str) -> str:
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return f.read()


def errors_scenario(args, words) -> int:
    """A swarm with a stack "transfers", a lone container and docker's own errors."""
    if words[:2] == ["service", "ls"]:
        sys.stdout.write(fixture("errors_services.jsonl"))
    elif words[:2] == ["stack", "ls"]:
        sys.stdout.write("transfers\n")
    elif words[:1] == ["ps"]:
        sys.stdout.write(fixture("errors_containers.jsonl"))
    elif words[:2] == ["service", "logs"] or words[:1] == ["logs"]:
        name = args[-1]
        if name == "broken-logs":
            sys.stderr.write("Error response from daemon: configured logging driver does not support reading\n")
            return 1
        sys.stdout.write(fixture(f"errors_logs_{name.split('.')[0]}.txt"))
    return 0


# Commands that answer a `--format '{"ID":{{json .ID}},...}'` template.
JSON_TABLES = {
    ("ps",): "ps.jsonl", ("container", "ls"): "ps.jsonl",
    ("images",): "images_table.jsonl", ("image", "ls"): "images_table.jsonl",
    ("service", "ls"): "service_ls.jsonl", ("service", "ps"): "service_ps.jsonl",
    ("node", "ls"): "node_ls.jsonl", ("stats",): "stats.jsonl",
}


def json_template(args, words) -> Optional[int]:
    """Fill a field-by-field JSON template like docker does; None if not one."""
    template = next((a for a in args if a.startswith('{"')), None)
    if template is None:
        return None
    words = [w for w in words if w != template]
    name = JSON_TABLES.get(tuple(words[:1])) or JSON_TABLES.get(tuple(words[:2]))
    if name is None:
        return None
    fields = re.findall(r"\{\{json \.(\w+)\}\}", template)
    # FAKE_OLD_DOCKER: a docker that lacks the fields, so dvt falls back.
    old = os.environ.get("FAKE_OLD_DOCKER")
    for line in fixture(name).splitlines():
        item = json.loads(line)
        for field in fields:
            if old or field not in item:
                sys.stderr.write(f'template parsing error: template: :1:2: executing "" at '
                                 f'<.{field}>: can\'t evaluate field {field} in type formatter\n')
                return 1
        sys.stdout.write(json.dumps({f: item[f] for f in fields}) + "\n")
    return 0


def main() -> int:
    args = sys.argv[1:]
    log = os.environ.get("FAKE_DOCKER_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as f:
            f.write(json.dumps(args) + "\n")

    words = [a for a in args if not a.startswith("-")]
    cmd = words[:2]
    json_format = "{{json .}}" in args
    # "swarm" serves the second recording: several tags per repository,
    # dangling images and failing services.
    swarm = os.environ.get("FAKE_SCENARIO") == "swarm"

    if os.environ.get("FAKE_SCENARIO") == "errors":
        return errors_scenario(args, words)

    if os.environ.get("FAKE_SCENARIO") != "swarm" or not ({"-q", "{{json .}}"} & set(args)):
        code = json_template(args, words)
        if code is not None:
            return code

    if swarm and cmd[:1] == ["ps"] and "-q" in args:
        sys.stdout.write(fixture("container_ids.txt"))
    elif swarm and cmd[:1] == ["inspect"] and "{{.Image}}" in args:
        sys.stdout.write(fixture("container_images.txt"))
    elif cmd[:1] == ["images"] and json_format:
        dangling = "dangling=true" in args
        sys.stdout.write(fixture("images_dangling.jsonl" if dangling else "images.jsonl"))
    elif cmd[:1] == ["rmi"]:
        if "fail" in args[-1]:
            sys.stderr.write(f"Error response from daemon: conflict: unable to remove {args[-1]}\n")
            return 1
        sys.stdout.write(f"Untagged: {args[-1]}\n")
    elif cmd == ["service", "ls"] and json_format:
        sys.stdout.write(fixture("services.jsonl"))
    elif cmd == ["service", "ps"] and json_format:
        sys.stdout.write(fixture(f"service_ps_{words[2]}.jsonl"))
    elif cmd == ["service", "inspect"] and json_format:
        sys.stdout.write(fixture("services_inspect.jsonl"))
    elif cmd[:1] == ["stats"]:
        if "--no-stream" not in args:
            while True:  # real docker stats never exits on its own
                time.sleep(1)
        sys.stdout.write(fixture("stats.txt"))
    elif cmd[:1] == ["ps"] and "-q" in args:
        sys.stdout.write("c1\nc2\n")
    elif cmd[:1] == ["ps"]:
        sys.stdout.write(fixture("ps_no_trunc.txt"))
    elif cmd[:1] == ["inspect"] and "--format" in args:
        # Both containers run alpine (sha256:294b683cb724...).
        sys.stdout.write("sha256:294b683cb724975bec92580e1e685676bd4b50bda910ddb8c51d4cabeaec77e6\n" * 2)
    elif cmd == ["service", "ls"]:
        sys.stdout.write(fixture("service_ls.txt"))
    elif cmd == ["service", "ps"]:
        sys.stdout.write(fixture("service_ps.txt"))
    elif cmd == ["node", "ls"]:
        sys.stdout.write(fixture("node_ls.txt"))
    elif cmd[:1] == ["images"] or cmd == ["image", "ls"]:
        name = "images_legacy.txt" if "--no-trunc" in args else "images_v29.txt"
        sys.stdout.write(fixture(name))
    elif cmd[:1] == ["inspect"]:
        sys.stdout.write(fixture("inspect_containers.json"))
    elif cmd == ["service", "inspect"]:
        sys.stdout.write(fixture("inspect_service.json"))
    elif cmd[:1] == ["logs"]:
        sys.stdout.write("2026-10-06T08:00:00Z INFO started job\n")
        sys.stdout.write("WARN slow query\n")
        sys.stdout.flush()
        sys.stderr.write("ERROR failed to connect to db\n")
    else:
        sys.stderr.write(f"docker: unknown command: docker {' '.join(args)}\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
