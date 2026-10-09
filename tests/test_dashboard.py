from dkview import ansi
from dkview.features import dashboard
from dkview.options import Options
from dkview.transform import is_task_container

TASK = "rhl9m97o2vw5ojx4gfxs6o2z0"
NODE = "n48cf8f534zmpq2l7c0y6v1ab"


def _data():
    def c(name, state, status):
        return {"ID": name[:12], "Names": name, "Image": "busybox", "State": state,
                "Status": status, "Ports": ""}
    return {
        "info": [{"ServerVersion": "29.8.2", "Name": "vm", "NCPU": 4, "MemTotal": 0}],
        "ps": [
            c("api.1." + TASK, "running", "Up 2 minutes"),
            c("api.1." + TASK[::-1], "exited", "Exited (255) 3 minutes ago"),
            c("agent." + NODE + "." + TASK, "exited", "Exited (1) 5 minutes ago"),
            c("checkout", "exited", "Exited (1) 1 minute ago"),
        ],
        "stats": [], "df": [],
        "services": [{"Name": "api", "Mode": "replicated", "Replicas": "1/1", "Image": "x"}],
    }


def test_task_containers_are_recognised():
    assert is_task_container("api.1." + TASK)
    assert is_task_container("agent." + NODE + "." + TASK)
    assert not is_task_container("checkout")
    assert not is_task_container("web.1")


def test_dead_swarm_tasks_are_not_problems(monkeypatch):
    monkeypatch.setattr(dashboard, "collect", _data)
    out = ansi.strip(dashboard.frame(Options(width=100)))
    assert "Needs attention (1)" in out
    assert "container checkout" in out
    assert "Containers: 1 running · 1 failed" in out
    assert "2 stopped swarm task containers not shown" in out
    assert TASK[::-1] not in out
