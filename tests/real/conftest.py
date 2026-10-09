import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ENGINE = os.environ.get("DKVIEW_ENGINE") or "docker"
PODMAN = Path(ENGINE).name.startswith("podman")
sys.path.insert(0, str(ROOT / "src"))

COMPOSE = """\
version: "3.3"
services:
  api:
    image: busybox:latest
    command: ["sh", "-c", "i=0; while true; do i=$$((i+1)); echo \\"INFO request $$i ok\\"; echo \\"ERROR Timeout calling http://10.0.3.$$((i%7)):8080/accounts (order $$i)\\"; [ $$((i%2)) -eq 0 ] && echo \\"WARN Retrying shipment $$i\\" >&2; sleep 1; done"]
    deploy:
      replicas: 2
  worker:
    image: busybox:latest
    command: ["sh", "-c", "while true; do echo 'level=info msg=tick'; sleep 2; done"]
"""


def docker(*args, check=True):
    result = subprocess.run([ENGINE, *args], capture_output=True, text=True)
    if check and result.returncode != 0:
        raise RuntimeError(f"docker {' '.join(args)}: {result.stderr.strip()}")
    return result


def wait_for(condition, timeout=60, what="docker"):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return
        time.sleep(1)
    raise RuntimeError(f"timed out waiting for {what}")


def cleanup():
    if not PODMAN:
        docker("stack", "rm", "rt", check=False)
        docker("service", "rm", "rt_broken", check=False)
    docker("rm", "-f", "rt_web", "rt_done", check=False)
    docker("volume", "rm", "rt_data", check=False)
    wait_for(lambda: not docker("ps", "-aq", "--filter", "name=rt_", check=False).stdout.strip(),
             what="old rt_* containers to go away")


@pytest.fixture(scope="session")
def host(tmp_path_factory):
    if os.environ.get("REAL_DOCKER") != "1":
        pytest.skip("set REAL_DOCKER=1 to run tests against a real docker daemon")
    info = json.loads(docker("info", "--format", "{{json .}}").stdout)
    if PODMAN:
        cleanup()
        docker("volume", "create", "rt_data")
        docker("run", "-d", "--name", "rt_web", "--label", "team=orders", "busybox:latest",
               "sh", "-c", "echo 'fail: Web[0] System.InvalidOperationException: no'; sleep 100000")
        docker("run", "--name", "rt_done", "busybox:latest", "sh", "-c", "echo bye")
        yield "podman " + info["version"]["Version"]
        cleanup()
        return
    if info["Swarm"]["LocalNodeState"] != "active":
        docker("swarm", "init", "--advertise-addr", "127.0.0.1")
    cleanup()
    docker("volume", "create", "rt_data")

    compose = tmp_path_factory.mktemp("stack") / "stack.yml"
    compose.write_text(COMPOSE)
    docker("stack", "deploy", "-c", str(compose), "rt")
    docker("service", "create", "-d", "--name", "rt_broken", "--restart-max-attempts", "2",
           "--restart-delay", "1s", "busybox:latest", "sh", "-c", "echo boom; exit 3")
    docker("run", "-d", "--name", "rt_web", "-p", "18080:80", "--label", "team=orders",
           "busybox:latest", "sh", "-c", "echo 'fail: Web[0] System.InvalidOperationException: no'; sleep 100000")
    docker("run", "--name", "rt_done", "busybox:latest", "sh", "-c", "echo bye")

    def api_logs_errors():
        out = docker("service", "logs", "--raw", "rt_api", check=False).stdout
        return out.count("ERROR") >= 4

    wait_for(lambda: docker("service", "ls", "--filter", "name=rt_api", "--format",
                            "{{.Replicas}}").stdout.strip().startswith("2/2"),
             what="rt_api to run 2 replicas")
    wait_for(api_logs_errors, what="rt_api to log errors")
    wait_for(lambda: "Failed" in docker("service", "ps", "rt_broken", "--format",
                                        "{{.CurrentState}}").stdout,
             what="rt_broken to fail")
    yield info["ServerVersion"]
    cleanup()
