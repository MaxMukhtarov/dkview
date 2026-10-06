#!/usr/bin/env python3
"""Stand-in for the docker CLI, serving recorded output from tests/fixtures.

Every call's arguments are appended to $FAKE_DOCKER_LOG so tests can check
what pprint actually ran.
"""

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, "fixtures")


def fixture(name: str) -> str:
    with open(os.path.join(FIXTURES, name), encoding="utf-8") as f:
        return f.read()


def main() -> int:
    args = sys.argv[1:]
    log = os.environ.get("FAKE_DOCKER_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as f:
            f.write(json.dumps(args) + "\n")

    words = [a for a in args if not a.startswith("-")]
    cmd = words[:2]

    if cmd[:1] == ["stats"]:
        if "--no-stream" not in args:
            while True:  # real docker stats never exits on its own
                time.sleep(1)
        sys.stdout.write(fixture("stats.txt"))
    elif cmd[:1] == ["ps"]:
        sys.stdout.write(fixture("ps_no_trunc.txt"))
    elif cmd == ["service", "ls"]:
        sys.stdout.write(fixture("service_ls.txt"))
    elif cmd == ["service", "ps"]:
        sys.stdout.write(fixture("service_ps.txt"))
    elif cmd[:1] == ["images"]:
        sys.stdout.write(fixture("images_v29.txt"))
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
