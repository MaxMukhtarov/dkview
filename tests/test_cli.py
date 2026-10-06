"""End-to-end runs of `python -m pprint_docker` against a fake docker."""


def test_ps_table_with_shortcut(fake_docker):
    result = fake_docker.run("ps", "-a")
    assert result.returncode == 0
    assert "┌" in result.stdout and "NAMES" in result.stdout
    assert fake_docker.calls() == [["ps", "-a", "--no-trunc"]]
    # Full 64-character IDs are shortened back to 12.
    assert "26a04fd7c376e78" not in result.stdout


def test_stats_does_not_hang(fake_docker):
    # stdout is not a terminal here, so this prints one snapshot.
    result = fake_docker.run("docker", "stats", timeout=10)
    assert result.returncode == 0
    assert "CPU %" in result.stdout
    assert fake_docker.calls()[0][-1] == "--no-stream"


def test_unknown_command_passes_through(fake_docker):
    result = fake_docker.run("docker", "serivce", "ls")
    assert result.returncode == 1
    assert "unknown command" in result.stderr
    assert result.stdout == ""


def test_missing_program(fake_docker):
    result = fake_docker.run("definitely-not-a-program")
    assert result.returncode == 127
    assert "command not found" in result.stderr


def test_cols_sort_and_grep(fake_docker):
    result = fake_docker.run("--cols", "name,status", "--grep", "up", "--sort", "name", "ps", "-a")
    lines = [line for line in result.stdout.splitlines() if line.startswith("│")]
    assert lines[0].split("│")[1].strip() == "NAMES"
    names = [line.split("│")[1].strip() for line in lines[1:]]
    assert "oneshot" not in names  # exited, filtered out by --grep up
    assert names == sorted(names)


def test_bad_column_is_a_clear_error(fake_docker):
    result = fake_docker.run("--cols", "bogus", "ps")
    assert result.returncode == 2
    assert "no column matches 'bogus'" in result.stderr


def test_logs_merge_stderr_and_filter(fake_docker):
    result = fake_docker.run("--grep", "error|warn", "logs", "web")
    assert result.stdout.splitlines() == ["WARN slow query", "ERROR failed to connect to db"]


def test_inspect_summary(fake_docker):
    result = fake_docker.run("inspect", "web", "sick")
    assert "running (healthy)" in result.stdout
    assert "running (unhealthy)" in result.stdout
    assert "--full" in result.stdout


def test_inspect_full_tree(fake_docker):
    result = fake_docker.run("--full", "inspect", "web")
    assert "├─ State" in result.stdout


def test_pprint_opts_env(fake_docker):
    result = fake_docker.run("ps", env={"PPRINT_OPTS": "--cols name"})
    header = next(line for line in result.stdout.splitlines() if line.startswith("│"))
    assert header.count("│") == 2


def test_shell_init(fake_docker):
    result = fake_docker.run("shell-init", "bash")
    assert "command pprint docker" in result.stdout
    assert "[ -t 1 ]" in result.stdout
