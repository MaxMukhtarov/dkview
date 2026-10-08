"""`docker images`: in-use marks, image data and the grouped view."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Sequence, Set

from .. import docker
from ..formats import fields_template
from ..ansi import BOLD, DIM, GREEN, paint
from ..layout import render
from ..options import Options
from ..runner import capture
from ..styles import styler
from ..table import Table
from ..transform import select_columns, short_image, sort_rows
from ..units import ago, human_size, parse_docker_time, parse_size

IN_USE = "●"
NOT_IN_USE = "○"

def legend() -> str:
    return (paint(IN_USE, GREEN) + " used by a container   "
            + paint(NOT_IN_USE, DIM) + " not used")


def is_image_list(argv: Sequence[str]) -> bool:
    w = docker.words(argv)
    return w[:1] == ["images"] or w[:2] in (["image", "ls"], ["image", "list"])


def global_options(argv: Sequence[str]) -> List[str]:
    """`docker --context prod images` -> ['docker', '--context', 'prod']."""
    first = docker.words(argv, limit=1)
    if not first:
        return list(argv[:1])
    return list(argv[:list(argv).index(first[0])])


def used_image_ids(argv: Sequence[str]) -> Optional[Set[str]]:
    """Image IDs of all containers, running or stopped (12 hex characters).

    Returns None when docker can't be asked, so nothing gets marked.
    """
    base = global_options(argv)
    ids = capture(base + ["ps", "-a", "-q", "--no-trunc"])
    if ids.code != 0:
        return None
    containers = ids.stdout.split()
    if not containers:
        return set()
    images = capture(base + ["inspect", "--format", "{{.Image}}"] + containers)
    if images.code != 0 and not images.stdout.strip():
        return None
    return {line.strip().split(":")[-1][:12]
            for line in images.stdout.splitlines() if line.strip()}


def mark_in_use(table: Table, used: Set[str]) -> bool:
    """Put ● (in use) or ○ (not used) before each image name."""
    id_col = table.column("IMAGE ID")
    if id_col is None:
        id_col = table.column("ID")
    name_col = table.column("REPOSITORY")
    if name_col is None:
        name_col = table.column("IMAGE")
    if id_col is None or name_col is None:
        return False

    for row in table.rows:
        image_id = row[id_col].split(":")[-1][:12]
        mark = IN_USE if image_id in used else NOT_IN_USE
        row[name_col] = f"{mark} {row[name_col]}"
    return True


# ------------------------------------------------------------ image data

@dataclass
class ImageInfo:
    repository: str
    tag: str
    id: str              # 12 hex characters
    created: Optional[datetime]
    size: float          # bytes
    in_use: bool = False

    @property
    def dangling(self) -> bool:
        return self.repository == "<none>"

    @property
    def reference(self) -> str:
        """What to pass to `docker rmi`: repo:tag, or the ID for dangling images."""
        if self.dangling or self.tag == "<none>":
            return self.id
        return f"{self.repository}:{self.tag}"


def _json_lines(text: str) -> List[dict]:
    items = []
    for line in text.splitlines():
        try:
            items.append(json.loads(line))
        except ValueError:
            pass
    return items


def load_images(argv: Sequence[str]) -> Optional[List[ImageInfo]]:
    """Every tagged image plus dangling ones, with in-use flags.

    Returns None (after printing docker's error) when docker can't be asked.
    """
    base = global_options(argv)
    fmt = ["--no-trunc", "--format",
           fields_template(["Repository", "Tag", "ID", "CreatedAt", "Size"])]
    tagged = capture(base + ["images"] + fmt)
    if tagged.code != 0:
        sys.stderr.write(tagged.stderr)
        return None
    dangling = capture(base + ["images", "--filter", "dangling=true"] + fmt)
    used = used_image_ids(argv) or set()

    seen = set()
    result = []
    for item in _json_lines(tagged.stdout) + _json_lines(dangling.stdout):
        image_id = str(item.get("ID", "")).split(":")[-1][:12]
        key = (item.get("Repository"), item.get("Tag"), image_id)
        if key in seen:
            continue
        seen.add(key)
        result.append(ImageInfo(
            repository=item.get("Repository", ""),
            tag=item.get("Tag", ""),
            id=image_id,
            created=parse_docker_time(item.get("CreatedAt", "")),
            size=parse_size(item.get("Size", "")),
            in_use=image_id in used,
        ))
    return result


def newest_first(images: Iterable[ImageInfo]) -> List[ImageInfo]:
    oldest = datetime.min.replace(tzinfo=timezone.utc)
    return sorted(images, key=lambda i: i.created or oldest, reverse=True)


def by_repository(images: Iterable[ImageInfo]) -> Dict[str, List[ImageInfo]]:
    groups: Dict[str, List[ImageInfo]] = {}
    for image in images:
        groups.setdefault(image.repository, []).append(image)
    return {repo: newest_first(items) for repo, items in groups.items()}


def unique_size(images: Iterable[ImageInfo]) -> float:
    """Total size, counting an image ID once even if it has several tags."""
    sizes = {i.id: i.size for i in images}
    return sum(sizes.values())


# --------------------------------------------------------- grouped view

def group_table(images: List[ImageInfo], short: bool) -> Table:
    table = Table(["REPOSITORY", "TAGS", "NEWEST TAG", "NEWEST", "IN USE",
                   "TOTAL SIZE", "UNUSED SIZE"])
    groups = by_repository(images)
    order = sorted(groups, key=lambda r: unique_size(groups[r]), reverse=True)
    for repo in order:
        items = groups[repo]
        newest = items[0]
        in_use = [i for i in items if i.in_use]
        used_ids = {i.id for i in in_use}
        unused = [i for i in items if i.id not in used_ids]
        name = short_image(repo) if short else repo
        table.rows.append([
            f"{IN_USE if in_use else NOT_IN_USE} {name}",
            str(len(items)),
            "" if newest.dangling else newest.tag,
            ago(newest.created),
            f"{len(in_use)} of {len(items)}",
            human_size(unique_size(items)),
            human_size(unique_size(unused)) if unused else "",
        ])
    return table


def run_group(argv: Sequence[str], opts: Options) -> int:
    images = load_images(argv)
    if images is None:
        return 1
    if opts.grep:
        images = [i for i in images if opts.grep.search(f"{i.repository}:{i.tag}")]
    table = group_table(images, opts.short)
    if opts.sort:
        sort_rows(table, opts.sort, opts.desc)
    if opts.cols:
        table = select_columns(table, opts.cols)

    total = unique_size(images)
    unused = unique_size(i for i in images if not i.in_use)
    sys.stdout.write(render(table, opts.width, styler) + "\n")
    sys.stdout.write(legend() + "\n")
    ids = len({i.id for i in images})
    count = f"{len(images)} images" if ids == len(images) else f"{len(images)} tags of {ids} images"
    sys.stdout.write(
        f"{count} in {len(table.rows)} repositories, "
        f"{human_size(total)} in total, " + paint(f"{human_size(unused)} not used", BOLD)
        + paint("  (sizes can share layers, so real savings may be smaller)", DIM) + "\n")
    return 0
