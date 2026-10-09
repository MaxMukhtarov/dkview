import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from dkview.features import errors
from dkview.options import Options

ERRORS = {"FAKE_SCENARIO": "errors"}
NOW = datetime(2026, 10, 7, 18, 30, tzinfo=timezone.utc)
FIXTURES = Path(__file__).parent / "fixtures"


def _jsonl(name):
    return [json.loads(line) for line in (FIXTURES / name).read_text(encoding="utf-8").splitlines()]


@pytest.mark.parametrize("text, seconds", [
    ("30m", 1800), ("2d", 172800), ("1w", 604800), ("1h30m", 5400), ("45s", 45),
    ("2x", None), ("", None), ("2026-10-07", None),
])
def test_parse_since(text, seconds):
    assert errors.parse_since(text) == seconds


def test_days_are_converted_for_docker():
    assert errors.since_for_docker("2d") == "172800s"
    assert errors.since_for_docker("2026-10-07T09:00") == "2026-10-07T09:00"


def test_levels():
    assert errors.level("2026-10-07T18:00:03+00:00 ERROR Timeout") == "error"
    assert errors.level("fail: Checkout.Api[0] boom") == "error"
    assert errors.level('level=warn msg="slow"') == "warn"
    assert errors.level("System.TimeoutException: timed out") == "error"
    assert errors.level("INFO handled ValidationError fine") is None
    assert errors.level("      at Checkout.Api.Catalog.Find(Guid id)") is None


def test_repeats_share_a_signature():
    a = "2026-10-07T18:00:03+00:00 ERROR Timeout calling http://10.0.3.3:8080/x after 30000ms (order 3)"
    b = "2026-10-07T18:00:09+00:00 ERROR Timeout calling http://10.0.3.2:8080/x after 30000ms (order 9)"
    assert errors.signature(a) == errors.signature(b)
    assert errors.signature("request 4f3a2-9c failed") == errors.signature("request 4f3a194-9c failed")
    assert errors.signature("ERROR db down") != errors.signature("ERROR cache down")


def test_source_counts_groups_and_docker_messages(fixture_lines):
    source = errors.Source("orders_api", "service", [])
    for line in fixture_lines("errors_logs_orders_api.txt"):
        source.add(line)
    source.add("Error response from daemon: No such service")
    assert (source.errors, source.warnings, source.lines) == (4, 1, 7)
    assert len(source.groups) == 3
    timeout = max(source.groups.values(), key=lambda g: g.count)
    assert timeout.count == 3
    assert "(order 9)" in timeout.message
    assert not timeout.message.startswith("2026")
    assert source.problem == "Error response from daemon: No such service"


def test_grep_counts_only_matching_lines(fixture_lines):
    import re
    source = errors.Source("orders_api", "service", [])
    for line in fixture_lines("errors_logs_orders_api.txt"):
        source.add(line, re.compile("npgsql", re.I))
    assert (source.errors, source.warnings) == (1, 0)


def test_report_layout(fixture_lines):
    api = errors.Source("orders_api", "service", [])
    for line in fixture_lines("errors_logs_orders_api.txt"):
        api.add(line)
    quiet = errors.Source("traefik", "service", [])
    out = errors.render_report([quiet, api], Options(width=100), "30m", now=NOW)
    assert out.splitlines()[0] == ("Errors and warnings, last 30m: 4 errors · 1 warning "
                                   "in 1 of 2 sources")
    assert "✗ orders_api  service · 4 errors · 1 warning · 3 different messages" in out
    assert "│ 3×    │ error │ 29m ago │ 29m ago │ ERROR Timeout calling" in out
    assert {len(line) for line in out.splitlines() if line.startswith("  ┌")} == {100}


def test_quiet_sources_wrap_to_the_width(fixture_lines):
    api = errors.Source("orders_api", "service", [])
    for line in fixture_lines("errors_logs_orders_api.txt"):
        api.add(line)
    quiet = [errors.Source("quiet-" + "x" * 12 + str(i), "service", []) for i in range(6)]
    out = errors.render_report(quiet + [api], Options(width=70), "30m", now=NOW)
    wrapped = [l for l in out.splitlines() if "quiet-" in l]
    assert len(wrapped) > 1
    assert max(len(l) for l in wrapped) <= 70
    assert wrapped[1].startswith(" " * len("x nothing in "))


def _resolve(*targets):
    host = errors.Host(
        stacks=["orders"],
        services=_jsonl("errors_services.jsonl"),
        containers=_jsonl("errors_containers.jsonl"),
    )
    sources, missing = errors.resolve(host, ["docker"], targets, "1800s")
    return [(s.kind, s.name) for s in sources], missing, host


def test_resolve_stack_service_container_and_ids():
    found, missing, _ = _resolve("orders", "traefik", "checkout", "9a8b7c")
    assert found == [("service", "orders_api"), ("service", "orders_worker"),
                     ("service", "traefik"), ("container", "checkout")]
    assert missing == []


def test_resolve_full_service_id_and_unknown_and_ambiguous():
    found, missing, _ = _resolve("rhl9m97o2vw5ojx4gfxs6o2z0", "nope", "9a")
    assert found == [("service", "orders_api")]
    assert missing == ["nope", "9a"]
    found, missing, _ = _resolve("9a1")
    assert found == [("container", "quiet-box")]


def test_everything_skips_swarm_task_containers():
    _, _, host = _resolve()
    names = [s.name for s in errors.everything(host, ["docker"], "1800s")]
    assert names == ["orders_api", "orders_worker", "traefik", "checkout", "quiet-box"]


def test_errors_for_the_whole_host(fake_docker):
    result = fake_docker.run("errors", env=ERRORS)
    assert result.returncode == 1, result.stderr
    out = result.stdout
    assert out.startswith("Errors and warnings, last 30m: 7 errors · 1 warning in 2 of 5 sources")
    assert "✓ nothing in orders_worker, quiet-box, traefik" in out
    assert "System.TimeoutException" in out
    logs = [c for c in fake_docker.calls() if "logs" in c]
    assert ["service", "logs", "--raw", "--timestamps", "--since", "1800s", "orders_api"] in logs
    assert ["logs", "--timestamps", "--since", "1800s", "checkout"] in logs
    assert not any("orders_api.1.rczbwd3j5upexqmiy9xgcx6sj" in c for c in logs)


def test_errors_for_a_stack_with_options_after_it(fake_docker):
    result = fake_docker.run("errors", "orders", "--since", "2d", env=ERRORS)
    assert result.returncode == 1
    assert result.stdout.startswith("Errors and warnings, last 2d: 4 errors · 1 warning")
    assert "checkout" not in result.stdout
    assert all("172800s" in c for c in fake_docker.calls() if "logs" in c)


def test_errors_since_before_the_command(fake_docker):
    result = fake_docker.run("--since", "6h", "errors", "checkout", env=ERRORS)
    assert "last 6h: 3 errors in 1 source" in result.stdout


def test_errors_unknown_target_and_bad_since(fake_docker):
    result = fake_docker.run("errors", "nope", env=ERRORS)
    assert result.returncode == 2
    assert "no stack, service or container called nope" in result.stderr
    result = fake_docker.run("errors", "--since", "2x", env=ERRORS)
    assert result.returncode == 2 and "--since 2x" in result.stderr


def test_errors_clean_target_exits_zero(fake_docker):
    result = fake_docker.run("errors", "orders_worker", env=ERRORS)
    assert result.returncode == 0
    assert "none in 1 source" in result.stdout


@pytest.mark.skipif(os.name == "nt", reason="uses sh")
def test_logs_that_never_finish_are_cut_off():
    import time
    source = errors.Source("api", "service", [
        "sh", "-c", "echo '2026-10-07T18:00:01.0Z ERROR boom'; exec sleep 30"])
    started = time.time()
    errors.read(source, idle=0.5, first=5)
    assert time.time() - started < 4
    assert source.errors == 1
    assert "stopped sending logs" in source.problem


@pytest.mark.skipif(os.name == "nt", reason="uses sh")
def test_slow_first_line_is_waited_for():
    source = errors.Source("api", "service", [
        "sh", "-c", "sleep 1; echo '2026-10-07T18:00:01.0Z ERROR boom'"])
    errors.read(source, idle=0.5, first=5)
    assert source.errors == 1 and source.problem == ""
