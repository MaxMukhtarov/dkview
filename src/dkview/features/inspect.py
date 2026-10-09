from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from ..ansi import BOLD, CYAN, DIM, GREEN, MAGENTA, RED, YELLOW, paint
from ..layout import render_plain_rows
from ..options import Options
from ..runner import capture

Section = Tuple[str, List[Tuple[str, str]]]


def tree(value: Any, name: str = "", prefix: str = "", last: bool = True,
         top: bool = True) -> List[str]:
    lines: List[str] = []
    branch = "" if top else ("└─ " if last else "├─ ")
    label = paint(name, CYAN) if name else ""

    if isinstance(value, dict) and value:
        if label:
            lines.append(prefix + branch + label)
        children = list(value.items())
        child_prefix = prefix + ("" if top else ("   " if last else "│  "))
        for i, (k, v) in enumerate(children):
            lines += tree(v, str(k), child_prefix, i == len(children) - 1, False)
        return lines

    if isinstance(value, list) and value and not _is_short_scalar_list(value):
        if label:
            lines.append(prefix + branch + label + paint(f"  [{len(value)}]", DIM))
        child_prefix = prefix + ("" if top else ("   " if last else "│  "))
        for i, item in enumerate(value):
            lines += tree(item, f"[{i}]", child_prefix, i == len(value) - 1, False)
        return lines

    text = _scalar(value)
    lines.append(prefix + branch + (label + ": " if label else "") + text)
    return lines


def _is_short_scalar_list(value: List[Any]) -> bool:
    return (all(not isinstance(v, (dict, list)) for v in value)
            and len(json.dumps(value)) <= 80)


def _scalar(value: Any) -> str:
    if isinstance(value, bool) or value is None:
        return paint(json.dumps(value), MAGENTA)
    if isinstance(value, (int, float)):
        return paint(str(value), YELLOW)
    if isinstance(value, list):
        return "[" + ", ".join(_scalar(v) for v in value) + "]"
    if isinstance(value, dict):
        return paint("{}", DIM)
    return paint(str(value), GREEN) if value != "" else paint('""', DIM)


def _get(obj: Any, path: str, default: Any = None) -> Any:
    for key in path.split("."):
        if not isinstance(obj, dict) or key not in obj:
            return default
        obj = obj[key]
    return obj if obj is not None else default


def parse_time(text: str) -> Optional[datetime]:
    if not text or text.startswith("0001-"):
        return None
    m = re.match(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(\.\d+)?(Z|[+-]\d\d:\d\d)?", text)
    if not m:
        return None
    base = datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S")
    zone = m.group(3) or "Z"
    if zone == "Z":
        return base.replace(tzinfo=timezone.utc)
    sign = 1 if zone[0] == "+" else -1
    hours, minutes = int(zone[1:3]), int(zone[4:6])
    return (base - sign * timedelta(hours=hours, minutes=minutes)).replace(tzinfo=timezone.utc)


def ago(text: str) -> str:
    when = parse_time(text)
    if not when:
        return ""
    seconds = int((datetime.now(timezone.utc) - when).total_seconds())
    for unit, size in (("y", 31536000), ("mo", 2592000), ("d", 86400),
                       ("h", 3600), ("m", 60), ("s", 1)):
        if seconds >= size:
            return f"{seconds // size}{unit} ago"
    return "just now"


def human_bytes(n: Any) -> str:
    try:
        size = float(n)
    except (TypeError, ValueError):
        return ""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1000 or unit == "TB":
            return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1000
    return ""


def _no_digest(image: str) -> str:
    return re.sub(r"@sha256:[0-9a-f]{64}", "", image or "")


def _labels(labels: Optional[Dict[str, str]]) -> List[Tuple[str, str]]:
    return sorted((labels or {}).items())


def _env(env: Optional[List[str]]) -> List[Tuple[str, str]]:
    pairs = []
    for item in env or []:
        key, _, value = item.partition("=")
        pairs.append((key, value))
    return pairs


def _cmd(*parts: Any) -> str:
    words: List[str] = []
    for part in parts:
        if isinstance(part, list):
            words += [str(p) for p in part]
        elif part:
            words.append(str(part))
    return " ".join(words)


def container_summary(c: Dict[str, Any]) -> Tuple[str, List[Section]]:
    name = c.get("Name", "").lstrip("/")
    state = c.get("State") or {}
    health = _get(state, "Health.Status")

    status = state.get("Status", "")
    if health:
        status += f" ({health})"
    if status.startswith("exited"):
        status += f", exit code {state.get('ExitCode')}"

    overview = [
        ("ID", c.get("Id", "")[:12]),
        ("Image", _no_digest(_get(c, "Config.Image", ""))),
        ("Status", status),
        ("Started", ago(state.get("StartedAt", ""))),
        ("Finished", ago(state.get("FinishedAt", "")) if status.startswith("exited") else ""),
        ("Restarts", str(c.get("RestartCount", 0))),
        ("Restart policy", _get(c, "HostConfig.RestartPolicy.Name", "")),
        ("Command", _cmd(_get(c, "Config.Entrypoint"), _get(c, "Config.Cmd"))),
        ("Working dir", _get(c, "Config.WorkingDir", "")),
        ("User", _get(c, "Config.User", "")),
        ("Memory limit", human_bytes(_get(c, "HostConfig.Memory")) if _get(c, "HostConfig.Memory") else ""),
        ("CPU limit", f"{_get(c, 'HostConfig.NanoCpus') / 1e9:g} CPUs" if _get(c, "HostConfig.NanoCpus") else ""),
    ]

    if health and health != "healthy":
        log = _get(state, "Health.Log") or []
        if log:
            output = " ".join(str(log[-1].get("Output", "")).split())
            overview.append(("Last health check", output[:300] or f"exit code {log[-1].get('ExitCode')}"))

    ports = []
    for port, bindings in sorted((_get(c, "NetworkSettings.Ports") or {}).items()):
        if not bindings:
            ports.append((port, "not published"))
        for b in bindings or []:
            ports.append((f"{b.get('HostIp') or '*'}:{b.get('HostPort')}", "→ " + port))

    networks = [(net, info.get("IPAddress") or "")
                for net, info in sorted((_get(c, "NetworkSettings.Networks") or {}).items())]

    mounts = [(m.get("Destination", ""),
               f"{m.get('Type')}: {m.get('Name') or m.get('Source')}"
               + ("" if m.get("RW", True) else " (read-only)"))
              for m in c.get("Mounts") or []]

    return f"{name}  container", [
        ("", overview),
        ("Ports", ports),
        ("Networks", networks),
        ("Mounts", mounts),
        ("Environment", _env(_get(c, "Config.Env"))),
        ("Labels", _labels(_get(c, "Config.Labels"))),
    ]


def image_summary(i: Dict[str, Any]) -> Tuple[str, List[Section]]:
    tags = i.get("RepoTags") or []
    overview = [
        ("ID", i.get("Id", "").split(":")[-1][:12]),
        ("Tags", ", ".join(tags)),
        ("Created", ago(i.get("Created", ""))),
        ("Size", human_bytes(i.get("Size"))),
        ("Platform", "/".join(p for p in (i.get("Os"), i.get("Architecture"), i.get("Variant")) if p)),
        ("Layers", str(len(_get(i, "RootFS.Layers") or []))),
        ("Command", _cmd(_get(i, "Config.Entrypoint"), _get(i, "Config.Cmd"))),
        ("Working dir", _get(i, "Config.WorkingDir", "")),
        ("User", _get(i, "Config.User", "")),
        ("Exposed ports", ", ".join(sorted((_get(i, "Config.ExposedPorts") or {}).keys()))),
    ]
    return f"{tags[0] if tags else overview[0][1]}  image", [
        ("", overview),
        ("Environment", _env(_get(i, "Config.Env"))),
        ("Labels", _labels(_get(i, "Config.Labels"))),
    ]


def service_summary(s: Dict[str, Any]) -> Tuple[str, List[Section]]:
    spec = s.get("Spec") or {}
    container = _get(spec, "TaskTemplate.ContainerSpec") or {}
    if "Replicated" in (spec.get("Mode") or {}):
        mode = f"replicated, {_get(spec, 'Mode.Replicated.Replicas', 0)} replicas"
    else:
        mode = ", ".join((spec.get("Mode") or {}).keys()).lower()

    overview = [
        ("ID", s.get("ID", "")[:12]),
        ("Image", _no_digest(container.get("Image", ""))),
        ("Mode", mode),
        ("Created", ago(s.get("CreatedAt", ""))),
        ("Updated", ago(s.get("UpdatedAt", ""))),
        ("Update status", _get(s, "UpdateStatus.State", "")),
        ("Command", _cmd(container.get("Command"), container.get("Args"))),
        ("Constraints", ", ".join(_get(spec, "TaskTemplate.Placement.Constraints") or [])),
        ("Memory limit", human_bytes(_get(spec, "TaskTemplate.Resources.Limits.MemoryBytes"))
         if _get(spec, "TaskTemplate.Resources.Limits.MemoryBytes") else ""),
    ]
    ports = [(f"*:{p.get('PublishedPort')}", f"→ {p.get('TargetPort')}/{p.get('Protocol')}")
             for p in _get(s, "Endpoint.Ports") or []]
    mounts = [(m.get("Target", ""), f"{m.get('Type')}: {m.get('Source', '')}")
              for m in container.get("Mounts") or []]
    networks = [(n.get("Target", ""), ", ".join(n.get("Aliases") or []))
                for n in _get(spec, "TaskTemplate.Networks") or []]
    return f"{spec.get('Name', '')}  service", [
        ("", overview),
        ("Ports", ports),
        ("Networks", networks),
        ("Mounts", mounts),
        ("Environment", _env(container.get("Env"))),
        ("Labels", _labels(spec.get("Labels"))),
    ]


def kind_of(obj: Dict[str, Any]) -> Optional[Callable[[Dict[str, Any]], Tuple[str, List[Section]]]]:
    if "State" in obj and "Config" in obj and "HostConfig" in obj:
        return container_summary
    if "RepoTags" in obj and "RootFS" in obj:
        return image_summary
    if "Spec" in obj and "Endpoint" in obj:
        return service_summary
    return None


def _status_color(value: str) -> Optional[str]:
    v = value.lower()
    if "unhealthy" in v or v.startswith("dead") or (
            v.startswith("exited") and not v.endswith("exit code 0")):
        return RED
    if any(w in v for w in ("starting", "restarting", "paused")):
        return YELLOW
    if v.startswith("running"):
        return GREEN
    return DIM


def _value_style(key: str, value: str) -> str:
    if key == "Status":
        return paint(value, _status_color(value) or "")
    if key == "Last health check":
        return paint(value, YELLOW)
    return value


def render_summary(title: str, sections: List[Section]) -> str:
    out = [paint(title, BOLD)]
    for heading, pairs in sections:
        pairs = [(k, v) for k, v in pairs if v not in ("", None)]
        if not pairs:
            continue
        if heading:
            out.append("")
            out.append(paint(heading, BOLD) + paint(f"  ({len(pairs)})", DIM))
        rows = [[paint(k, CYAN), _value_style(k, v)] for k, v in pairs]
        out += ["  " + line for line in render_plain_rows(rows)]
    return "\n".join(out)


def run(argv: Sequence[str], opts: Options) -> int:
    result = capture(argv)
    if result.stderr:
        sys.stderr.write(result.stderr)
    try:
        data = json.loads(result.stdout)
    except ValueError:
        sys.stdout.write(result.stdout)
        return result.code

    if not isinstance(data, list):
        data = [data]

    blocks = []
    for obj in data:
        summary = None if opts.full or not isinstance(obj, dict) else kind_of(obj)
        if summary:
            blocks.append(render_summary(*summary(obj)))
        else:
            title = ""
            if isinstance(obj, dict):
                title = str(obj.get("Name") or _get(obj, "Spec.Name") or obj.get("ID")
                            or obj.get("Id") or "").lstrip("/")
            lines = tree(obj)
            blocks.append("\n".join(([paint(title, BOLD)] if title else []) + lines))

    sys.stdout.write(("\n\n" + paint("─" * 40, DIM) + "\n\n").join(blocks) + "\n")
    if not opts.full and any(isinstance(o, dict) and kind_of(o) for o in data):
        sys.stdout.write(paint("\n(summary; use dkview --full for every field)\n", DIM))
    return result.code
