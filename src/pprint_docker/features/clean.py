"""`pprint clean`: remove old, unused image tags, keeping the newest few."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import List, Sequence, Tuple

from ..ansi import BOLD, DIM, GREEN, RED, YELLOW, paint
from ..layout import render
from ..options import Options
from ..runner import capture
from ..table import Table
from ..transform import short_image
from ..units import ago, human_size
from .images import (IN_USE, NOT_IN_USE, ImageInfo, by_repository, global_options,
                     load_images)

DELETE = "delete"


@dataclass
class Decision:
    image: ImageInfo
    action: str  # "delete", "keep: in use", "keep: newest"


def plan(images: List[ImageInfo], keep: int) -> List[Decision]:
    """Decide per tag. Per repository the `keep` newest tags always stay,
    images used by any container (running or stopped) always stay, and
    the rest is deleted. Dangling images (<none>) are deleted when unused."""
    decisions = []
    for repo, items in by_repository(images).items():
        for rank, image in enumerate(items):
            if image.in_use:
                action = "keep: in use"
            elif image.dangling:
                action = DELETE
            elif rank < keep:
                action = "keep: newest"
            else:
                action = DELETE
            decisions.append(Decision(image, action))
    return decisions


def freed_space(decisions: List[Decision]) -> float:
    """Space released: an image ID only counts when every tag of it goes."""
    sizes = {}
    kept_ids = set()
    for d in decisions:
        if d.action == DELETE:
            sizes[d.image.id] = d.image.size
        else:
            kept_ids.add(d.image.id)
    return sum(size for image_id, size in sizes.items() if image_id not in kept_ids)


def _style(header: str, value: str):
    if header == "ACTION":
        if value == DELETE:
            return RED
        if value.endswith("in use"):
            return GREEN
        return DIM
    return None


def plan_table(decisions: List[Decision], short: bool, show_kept: bool) -> Table:
    table = Table(["REPOSITORY", "TAG", "IMAGE ID", "CREATED", "SIZE", "ACTION"])
    touched = {d.image.repository for d in decisions if d.action == DELETE}
    for d in decisions:
        if d.image.repository not in touched:
            continue
        if d.action != DELETE and not show_kept:
            continue
        repo = d.image.repository
        name = short_image(repo) if short else repo
        mark = IN_USE if d.image.in_use else NOT_IN_USE
        table.rows.append([f"{mark} {name}", d.image.tag, d.image.id,
                           ago(d.image.created), human_size(d.image.size), d.action])
    return table


def confirm(question: str) -> bool:
    if not sys.stdin.isatty():
        sys.stderr.write("pprint: not asking without a terminal; use --yes to delete "
                         "or --dry-run to only look.\n")
        return False
    try:
        answer = input(question)
    except EOFError:
        return False
    return answer.strip().lower() in ("y", "yes")


def remove(argv: Sequence[str], targets: List[ImageInfo]) -> Tuple[int, List[str]]:
    """Delete one reference at a time so one failure doesn't stop the rest."""
    base = global_options(argv)
    removed, errors = 0, []
    for image in targets:
        result = capture(base + ["rmi", image.reference])
        if result.code == 0:
            removed += 1
            sys.stdout.write(paint("  ✓ ", GREEN) + f"removed {image.reference}\n")
        else:
            message = " ".join(result.stderr.split()) or f"exit code {result.code}"
            errors.append(f"{image.reference}: {message}")
            sys.stdout.write(paint("  ✗ ", RED) + f"{image.reference}: {message}\n")
        sys.stdout.flush()
    return removed, errors


def run(argv: Sequence[str], opts: Options) -> int:
    images = load_images(argv)
    if images is None:
        return 1
    if opts.grep:
        images = [i for i in images if opts.grep.search(f"{i.repository}:{i.tag}")]

    decisions = plan(images, opts.keep)
    targets = [d.image for d in decisions if d.action == DELETE]
    if not targets:
        sys.stdout.write(paint("✓ Nothing to clean: ", GREEN)
                         + f"no unused tags beyond the newest {opts.keep} of each "
                         "repository, and no dangling images.\n")
        return 0

    table = plan_table(decisions, opts.short, show_kept=opts.full or opts.dry_run)
    sys.stdout.write(render(table, opts.width, _style) + "\n")

    freed = freed_space(decisions)
    repos = len({t.repository for t in targets})
    sys.stdout.write(
        paint(f"{len(targets)} images to delete", BOLD, RED) + f" in {repos} repositories, "
        + paint(f"up to {human_size(freed)} freed", BOLD)
        + paint(f"  (keeping the newest {opts.keep} per repository and every image "
                "a container uses)", DIM) + "\n")

    if opts.dry_run:
        sys.stdout.write(paint("Dry run: nothing was deleted.", YELLOW) + "\n")
        return 0
    if not opts.yes and not confirm(f"Delete these {len(targets)} images? [y/N] "):
        sys.stdout.write("Nothing was deleted.\n")
        return 1

    removed, errors = remove(argv, targets)
    summary = f"Removed {removed} of {len(targets)} images."
    sys.stdout.write("\n" + (paint(summary, GREEN) if not errors else paint(summary, YELLOW)) + "\n")
    return 0 if not errors else 1
