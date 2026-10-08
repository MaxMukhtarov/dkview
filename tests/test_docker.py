import pytest

from dvt.docker import classify, expand_shortcut, prepare, words


@pytest.mark.parametrize("command, expected", [
    ("docker ps -a", "table"),
    ("docker container ls", "table"),
    ("docker service ls", "table"),
    ("docker --context prod service ps api", "table"),
    ("docker compose -f prod.yml ps", "table"),
    ("docker system df", "table"),
    ("docker stats", "stats"),
    ("docker container stats web", "stats"),
    ("docker logs -f web", "logs"),
    ("docker service logs --tail 5 api", "logs"),
    ("docker compose logs", "logs"),
    ("docker inspect web", "inspect"),
    ("docker service inspect api", "inspect"),
    ("docker inspect --format {{.State.Status}} web", "passthrough"),
    ("docker ps --format {{.Names}}", "passthrough"),
    ("docker ps -q", "passthrough"),
    ("docker system df -v", "passthrough"),
    ("docker images --tree", "passthrough"),
    ("docker run -it ubuntu", "passthrough"),
    ("docker exec -it web sh", "passthrough"),
    ("docker events", "passthrough"),
    ("docker serivce ls", "passthrough"),
    ("docker ps --help", "passthrough"),
    ("docker", "passthrough"),
])
def test_classify(command, expected):
    assert classify(command.split()).name == expected


def test_table_format_is_still_a_table():
    assert classify(["docker", "ps", "--format", "table {{.Names}}"]).name == "table"


def test_words_skip_option_values():
    assert words("docker --context prod service ls".split()) == ["service", "ls"]
    assert words("docker ps -f status=exited".split()) == ["ps"]


def test_stats_gets_a_single_snapshot():
    assert prepare(["docker", "stats"], trunc=False)[-1] == "--no-stream"


def test_ps_gets_full_values_unless_asked_not_to():
    assert prepare(["docker", "ps"], trunc=False) == ["docker", "ps", "--no-trunc"]
    assert prepare(["docker", "ps"], trunc=True) == ["docker", "ps"]
    assert prepare(["docker", "ps", "--no-trunc"], trunc=False).count("--no-trunc") == 1


def test_no_trunc_only_where_docker_supports_it():
    for command in ("docker service ls", "docker volume ls", "docker node ls"):
        assert "--no-trunc" not in prepare(command.split(), trunc=False)


def test_shortcut():
    assert expand_shortcut(["ps", "-a"]) == ["docker", "ps", "-a"]
    assert expand_shortcut(["kubectl", "get", "pods"]) == ["kubectl", "get", "pods"]
