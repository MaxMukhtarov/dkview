"""Docker list commands (ps, images, service ls...) as formatted tables."""

from __future__ import annotations

import sys
from dataclasses import replace
from typing import Callable, Optional, Sequence, Set, Tuple

from .. import docker
from ..layout import render
from ..options import Options
from ..runner import capture
from ..styles import styler
from ..table import Table, parse
from ..transform import ColumnError, grep_rows, select_columns, sort_rows, tidy
from . import images


def build(argv: Sequence[str], opts: Options) -> Tuple[int, str, str]:
    """Run a table command and return (exit code, formatted text, stderr)."""
    prepared = docker.prepare(argv, opts.trunc) if docker.is_docker(argv) else list(argv)
    result = capture(prepared)

    if not result.stdout.strip():
        return result.code, result.stdout, result.stderr

    table = parse(result.stdout.splitlines())
    if table is None:
        return result.code, result.stdout, result.stderr

    used = None
    if docker.is_docker(argv) and images.is_image_list(argv):
        used = images.used_image_ids(argv)

    try:
        table, marked = reshape(table, opts, used,
                                added_no_trunc="--no-trunc" in prepared[len(argv):])
    except ColumnError as error:
        return 2, "", f"pprint: {error}\n"

    out = render(table, opts.width, styler) + "\n"
    if marked and table.rows:
        out += images.legend() + "\n"
    return result.code, out, result.stderr


def reshape(table: Table, opts: Options, used_images: Optional[Set[str]] = None,
            added_no_trunc: bool = False) -> Tuple[Table, bool]:
    tidy(table, humanize=False, short=opts.short, strip_digests=added_no_trunc)
    # Mark before --grep (so `--grep ○` finds unused images) and before
    # --cols (which may drop the IMAGE ID column the marks rely on).
    marked = used_images is not None and images.mark_in_use(table, used_images)
    if opts.grep:
        grep_rows(table, opts.grep)
    # Sort on the original values ("4 minutes ago") before compacting them.
    if opts.sort:
        sort_rows(table, opts.sort, opts.desc)
    if opts.humanize:
        tidy(table, humanize=True, short=False, strip_digests=False)
    if opts.cols:
        table = select_columns(table, opts.cols)
    return table, marked


def run(argv: Sequence[str], opts: Options) -> int:
    code, out, err = build(argv, opts)
    if err:
        sys.stderr.write(err)
    sys.stdout.write(out)
    return code


def snapshot(argv: Sequence[str], opts: Options) -> Callable[[int], str]:
    """Frame producer for live mode."""
    def frame(width: int) -> str:
        _, out, err = build(argv, replace(opts, width=opts.width or width))
        return out if out.strip() else err
    return frame
