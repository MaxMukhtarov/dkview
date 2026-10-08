"""Docker list commands (ps, images, service ls...) as formatted tables."""

from __future__ import annotations

import sys
from dataclasses import replace
from typing import Callable, List, Optional, Sequence, Set, Tuple

from .. import docker, formats
from ..layout import render
from ..options import Options
from ..runner import Result, capture
from ..styles import styler
from ..table import Table, parse
from ..transform import ColumnError, grep_rows, select_columns, sort_rows, tidy
from . import images


def build(argv: Sequence[str], opts: Options) -> Tuple[int, str, str]:
    """Run a table command and return (exit code, formatted text, stderr)."""
    prepared = docker.prepare(argv, opts.trunc) if docker.is_docker(argv) else list(argv)
    result, table = read_json(prepared)
    if result is not None and table is None:
        # A real failure (no daemon, no such service): report it as is.
        return result.code, result.stdout, result.stderr
    if result is None:
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


def read_json(prepared: List[str]) -> Tuple[Optional[Result], Optional[Table]]:
    """Ask docker for one JSON object per row.

    Returns (result, table) on success, (result, None) when docker failed
    for a real reason, and (None, None) when the text output should be
    read instead: a command without a JSON layout, or a docker too old to
    understand the template.
    """
    columns = formats.layout(prepared)
    if columns is None:
        return None, None
    result = capture(prepared + formats.format_args(columns))
    if result.code == 0:
        table = formats.to_table(columns, result.stdout)
        return (result, table) if table is not None else (None, None)
    if formats.is_format_error(result.stderr):
        return None, None
    return result, None


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
