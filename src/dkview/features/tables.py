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
    prepared = docker.prepare(argv, opts.trunc) if docker.is_docker(argv) else list(argv)
    result, table = read_json(prepared)
    if result is not None and table is None:
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
        return 2, "", f"dkview: {error}\n"

    out = render(table, opts.width, styler) + "\n"
    if marked and table.rows:
        out += images.legend() + "\n"
    return result.code, out, result.stderr


def read_json(prepared: List[str]) -> Tuple[Optional[Result], Optional[Table]]:
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
    tidy(table, humanize=False, short=opts.short, strip_digests=added_no_trunc,
         full=opts.full)
    # marks need IMAGE ID, which --cols may drop
    marked = used_images is not None and images.mark_in_use(table, used_images)
    if opts.grep:
        grep_rows(table, opts.grep)
    # sort before ages are compacted
    if opts.sort:
        sort_rows(table, opts.sort, opts.desc)
    if opts.humanize:
        tidy(table, humanize=True, short=False, strip_digests=False, full=opts.full)
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
    def frame(width: int) -> str:
        _, out, err = build(argv, replace(opts, width=opts.width or width))
        return out if out.strip() else err
    return frame
