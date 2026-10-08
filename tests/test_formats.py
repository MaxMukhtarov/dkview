"""Reading list commands as JSON, and falling back to text on old docker."""

import pytest

from pprint_docker import formats

OLD = {"FAKE_OLD_DOCKER": "1"}

COMMANDS = [
    ["ps", "-a"],
    ["images"],
    ["image", "ls"],
    ["service", "ls"],
    ["service", "ps", "api"],
    ["node", "ls"],
    ["stats"],
    ["--short", "--sort", "created", "ps"],
    ["--cols", "name,current,error", "--grep", "broken", "service", "ps", "api"],
]


@pytest.mark.parametrize("command", COMMANDS, ids=" ".join)
def test_json_and_text_give_the_same_table(fake_docker, command):
    new = fake_docker.run(*command)
    calls = fake_docker.calls()
    old = fake_docker.run(*command, env=OLD)
    assert new.returncode == old.returncode == 0, new.stderr + old.stderr
    assert new.stdout == old.stdout
    assert "┌" in new.stdout
    assert any("--format" in c for c in calls)           # JSON was used


def test_old_docker_falls_back_to_text(fake_docker):
    result = fake_docker.run("service", "ls", env=OLD)
    assert result.returncode == 0 and "REPLICAS" in result.stdout
    assert result.stderr == ""                            # the template error is hidden
    calls = fake_docker.calls()
    assert "--format" in calls[0] and "--format" not in calls[1]


def test_user_format_and_quiet_are_left_alone():
    assert formats.layout(["docker", "ps", "-q"]) is None
    assert formats.layout(["docker", "ps", "--format", "table {{.Names}}"]) is None
    assert formats.layout(["docker", "volume", "ls"]) is None
    assert formats.layout(["kubectl", "get", "pods"]) is None


def test_layout_extras():
    headers = lambda argv: [h for h, _ in formats.layout(argv)]  # noqa: E731
    assert headers(["docker", "ps", "-s"])[-1] == "SIZE"
    assert headers(["docker", "--context", "prod", "container", "ls"])[0] == "CONTAINER ID"
    assert headers(["docker", "images", "--digests"])[:4] == ["REPOSITORY", "TAG", "DIGEST", "IMAGE ID"]
    assert headers(["docker", "stack", "ps", "transfers"])[4] == "DESIRED STATE"


def test_template_names_each_field():
    template = formats.template(formats.NODES)
    assert template.startswith('{"ID":{{json .ID}},')
    assert '"Self":{{json .Self}}' in template
    assert "{{json .}}" not in template                  # would make ps slow


def test_tasks_and_nodes_look_like_docker():
    tasks = formats.to_table(formats.TASKS, "\n".join([
        '{"ID":"a","Name":"api.1","CurrentState":"Running"}',
        '{"ID":"b","Name":"api.1","CurrentState":"Failed","Error":"\\"boom\\""}',
        '{"ID":"c","Name":"api.2"}',
    ]))
    assert [r[1] for r in tasks.rows] == ["api.1", "\\_ api.1", "api.2"]
    assert tasks.rows[1][6] == '"boom"'
    nodes = formats.to_table(formats.NODES, '{"ID":"h0f4","Hostname":"vm","Self":true}\n'
                                            '{"ID":"k9x2","Hostname":"vm2","Self":false}')
    assert [r[0] for r in nodes.rows] == ["h0f4 *", "k9x2"]


def test_not_json_means_fall_back():
    assert formats.to_table(formats.SERVICES, "ID   NAME\nabc  api") is None
    empty = formats.to_table(formats.SERVICES, "")
    assert empty.headers[1] == "NAME" and empty.rows == []


def test_real_errors_are_not_mistaken_for_format_errors():
    assert formats.is_format_error("template: :1:2: executing \"\" at <.Foo>: can't evaluate field Foo")
    assert not formats.is_format_error("Error response from daemon: This node is not a swarm manager.")
    assert not formats.is_format_error("Cannot connect to the Docker daemon at unix:///var/run/docker.sock.")
