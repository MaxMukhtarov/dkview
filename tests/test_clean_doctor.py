"""pprint clean, pprint doctor and pprint images --group."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pprint_docker.features import doctor
from pprint_docker.features.clean import DELETE, freed_space, plan
from pprint_docker.features.images import ImageInfo, group_table
from pprint_docker.units import human_size, parse_docker_time, parse_size

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)
SWARM = {"FAKE_SCENARIO": "swarm"}


def image(repo, tag, image_id, days_old, size=100e6, in_use=False):
    return ImageInfo(repo, tag, image_id, NOW - timedelta(days=days_old), size, in_use)


API = [
    image("reg.uz/api", "v5", "e" * 12, 1),
    image("reg.uz/api", "v4", "d" * 12, 2),
    image("reg.uz/api", "v3", "c" * 12, 3),
    image("reg.uz/api", "v2", "b" * 12, 4, in_use=True),
    image("reg.uz/api", "v1", "a" * 12, 5),
]


# ------------------------------------------------------------------ units

def test_sizes_and_times():
    assert parse_size("281MB") == 281e6
    assert parse_size("1.5GiB") == 1.5 * 1024 ** 3
    assert parse_size("N/A") == 0
    assert human_size(281e6) == "281MB"
    assert human_size(6.83e6) == "6.83MB"
    assert parse_docker_time("2026-09-17 20:37:20 +0000 UTC") == datetime(
        2026, 9, 17, 20, 37, 20, tzinfo=timezone.utc)


# ------------------------------------------------------------------ clean

def actions(decisions):
    return {d.image.tag: d.action for d in decisions}


def test_keeps_newest_and_in_use():
    result = actions(plan(API, keep=3))
    assert result == {"v5": "keep: newest", "v4": "keep: newest", "v3": "keep: newest",
                      "v2": "keep: in use", "v1": DELETE}


def test_keep_one():
    result = actions(plan(API, keep=1))
    assert result["v5"] == "keep: newest"
    assert result["v2"] == "keep: in use"  # never deleted while a container uses it
    assert [t for t, a in result.items() if a == DELETE] == ["v4", "v3", "v1"]


def test_dangling_images_go_unless_used():
    images = [image("<none>", "<none>", "f" * 12, 9),
              image("<none>", "<none>", "9" * 12, 9, in_use=True)]
    result = [d.action for d in plan(images, keep=3)]
    assert result == [DELETE, "keep: in use"]
    assert images[0].reference == "f" * 12  # removed by ID


def test_shared_image_id_frees_nothing_while_another_tag_stays():
    images = [image("reg.uz/api", "v9", "1" * 12, 1), image("reg.uz/api", "old", "2" * 12, 9),
              image("reg.uz/mirror", "old", "2" * 12, 1)]
    decisions = plan(images, keep=1)
    assert actions(decisions)["old"] in (DELETE, "keep: newest")
    # api:old is deleted, but mirror:old keeps the same image, so no space is freed.
    assert freed_space(decisions) == 0


def test_clean_dry_run_deletes_nothing(fake_docker):
    result = fake_docker.run("clean", "--dry-run", env=SWARM)
    assert result.returncode == 0
    assert "Dry run: nothing was deleted." in result.stdout
    assert not any(call[0] == "rmi" for call in fake_docker.calls())


def test_clean_without_terminal_refuses(fake_docker):
    result = fake_docker.run("clean", env=SWARM, input="y\n")
    assert result.returncode == 1
    assert "use --yes" in result.stderr
    assert not any(call[0] == "rmi" for call in fake_docker.calls())


def test_clean_yes_removes_only_planned_images(fake_docker):
    result = fake_docker.run("clean", "--keep", "2", "--yes", env=SWARM)
    assert result.returncode == 0
    removed = [call[1] for call in fake_docker.calls() if call[0] == "rmi"]
    assert removed, result.stdout
    used = {line.split(":")[-1][:12] for line in
            (FIXTURES / "container_images.txt").read_text().split()}
    tags = {}
    for line in (FIXTURES / "images.jsonl").read_text().splitlines():
        item = json.loads(line)
        tags[f"{item['Repository']}:{item['Tag']}"] = item["ID"].split(":")[-1][:12]
    for ref in removed:
        assert tags.get(ref, ref) not in used, f"{ref} is used by a container"
    assert "Removed" in result.stdout


# ---------------------------------------------------------- images --group

def test_group_table_totals():
    table = group_table(API + [image("alpine", "latest", "7" * 12, 30, size=13e6)], short=False)
    api = table.rows[0]
    assert api[0] == "● reg.uz/api"
    assert api[1] == "5"
    assert api[2] == "v5"
    assert api[4] == "1 of 5"
    assert api[5] == "500MB"
    assert api[6] == "400MB"
    assert table.rows[1][0] == "○ alpine"


def test_group_flag_works_after_the_command(fake_docker):
    result = fake_docker.run("images", "--group", env=SWARM)
    assert result.returncode == 0
    assert "TOTAL SIZE" in result.stdout
    assert "registry.example.uz/team/api" in result.stdout
    assert "--group" not in json.dumps(fake_docker.calls())  # never passed to docker


# ----------------------------------------------------------------- doctor

def test_task_parsing():
    task = doctor.Task.from_json({
        "Name": "broken.1", "Node": "vm", "DesiredState": "Shutdown",
        "CurrentState": "Rejected 4 seconds ago",
        "Error": '"failed to resolve reference \\"x\\""'})
    assert task.state == "Rejected"
    assert task.when == "4s ago"
    assert task.failed
    assert task.error.startswith("failed to resolve")


def test_hints():
    assert "can't be pulled" in doctor.hint('failed to resolve reference "x"', "api")
    assert "exit 137" in doctor.hint("task: non-zero exit (137)", "api")
    assert "service logs api" in doctor.hint("task: non-zero exit (3)", "api")
    assert doctor.hint("something else", "api") == ""


def test_doctor_report(fake_docker):
    result = fake_docker.run("doctor", env=SWARM)
    assert result.returncode == 1  # a service is failing
    out = result.stdout
    assert "✗ broken" in out and "0/1 replicas" in out
    assert "failed to resolve reference" in out
    assert "non-zero exit (3)" in out
    assert "can't be pulled" in out
    # Identical errors are grouped into one row with a count.
    broken = out.split("✗ broken")[1].split("✗ ")[0]
    assert broken.count("failed to resolve reference") == 1


def test_doctor_full_lists_every_task(fake_docker):
    result = fake_docker.run("doctor", "--full", env=SWARM)
    assert "TASK" in result.stdout
    assert result.stdout.count("broken.1") >= 2
