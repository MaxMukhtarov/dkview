"""Command-line entry point: decide what to do with the command given."""

from __future__ import annotations

import argparse
import os
import re
import shlex
import sys
from typing import List, Optional, Sequence

from . import __version__, docker
from .ansi import colors
from .features import clean, dashboard, doctor, errors, images, inspect, live, logs, shell, tables
from .options import Options
from .runner import passthrough

EPILOG = """\
examples:
  dvt docker ps                 formatted, colored table
  dvt ps -a                     same; "docker" can be left out
  dvt --short --cols name,status,image ps
  dvt --sort cpu --desc stats   live stats, busiest first (Ctrl+C quits)
  dvt --watch service ls        redraw every 2 seconds
  dvt inspect web               short summary; add --full for every field
  dvt --grep timeout logs -f api
  dvt dash                      overview of the whole host (--watch for live)
  dvt images --group            one row per repository with total sizes
  dvt clean --dry-run           old unused image tags that would be removed
  dvt clean --keep 5            remove them, keeping the newest 5 per repository
  dvt doctor                    failing swarm services with the real error
  dvt errors                    errors and warnings in all logs, last 30 minutes
  dvt errors transfers --since 2d   one stack, service or container
  dvt shell-init                make plain "docker ps" use dvt

dvt's own options go before the command. Default options can be set in
the DVT_OPTS environment variable, e.g. DVT_OPTS="--short".
"""


# Commands that are dvt's own rather than docker's.
OWN_COMMANDS = {"dash", "clean", "doctor", "errors", "shell-init"}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="dvt",
        description="Readable, colored output for docker commands.",
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    view = p.add_argument_group("table view")
    view.add_argument("--cols", metavar="A,B,...",
                      help="show only these columns, in this order (names can be shortened)")
    view.add_argument("--sort", metavar="COL", help="sort rows by a column (numbers, sizes and ages sort by value)")
    view.add_argument("--desc", action="store_true", help="sort largest first")
    view.add_argument("--grep", metavar="REGEX",
                      help="keep only rows (or log lines) matching this, case-insensitive")
    view.add_argument("--short", action="store_true",
                      help="hide the registry host in image names")
    view.add_argument("--long-times", action="store_true",
                      help="keep docker's '4 minutes ago' instead of '4m ago'")
    view.add_argument("--trunc", action="store_true",
                      help="keep docker's own truncation of long values")
    view.add_argument("--width", type=int, help="table width (default: terminal width)")

    mode = p.add_argument_group("modes")
    mode.add_argument("-w", "--watch", action="store_true",
                      help="redraw the output every few seconds until Ctrl+C")
    mode.add_argument("-n", "--interval", type=float, default=2.0, metavar="SEC",
                      help="seconds between redraws (default: 2)")
    mode.add_argument("--once", action="store_true",
                      help="docker stats: print one snapshot instead of a live view")
    mode.add_argument("--full", action="store_true",
                      help="inspect: show every field as a tree instead of a summary")
    mode.add_argument("--raw", action="store_true",
                      help="run the command untouched")
    mode.add_argument("--group", action="store_true",
                      help="images: one row per repository with total and unused size")

    cleaning = p.add_argument_group("dvt clean")
    cleaning.add_argument("--keep", type=int, default=3, metavar="N",
                       help="keep the newest N tags of each repository (default: 3)")
    cleaning.add_argument("--dry-run", action="store_true",
                       help="only show what would be deleted")
    cleaning.add_argument("-y", "--yes", action="store_true",
                       help="delete without asking")

    logs_group = p.add_argument_group("dvt errors")
    logs_group.add_argument("--since", metavar="TIME",
                            help="how far back to read logs: 30m, 6h, 2d, 1w or a date "
                                 f"(default: {errors.DEFAULT_SINCE})")

    out = p.add_argument_group("output")
    out.add_argument("--no-color", action="store_true", help="disable colors")
    out.add_argument("--color", action="store_true",
                     help="force colors even when not printing to a terminal")
    out.add_argument("-V", "--version", action="version", version=f"dvt {__version__}")

    p.add_argument("command", nargs=argparse.REMAINDER, help="the command to run")
    return p


def to_options(args: argparse.Namespace) -> Options:
    return Options(
        width=args.width,
        cols=[c.strip() for c in (args.cols or "").split(",") if c.strip()],
        sort=args.sort,
        desc=args.desc,
        grep=re.compile(args.grep, re.IGNORECASE) if args.grep else None,
        short=args.short,
        humanize=not args.long_times,
        trunc=args.trunc,
        watch=args.watch,
        once=args.once,
        interval=max(0.5, args.interval),
        full=args.full,
        group=args.group,
        keep=max(0, args.keep),
        dry_run=args.dry_run,
        yes=args.yes,
        since=args.since,
    )


def run(argv: Sequence[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(shlex.split(os.environ.get("DVT_OPTS", "")) + list(argv))

    if args.no_color:
        colors.enabled = False
    elif args.color:
        colors.enabled = True

    try:
        opts = to_options(args)
    except re.error as error:
        parser.error(f"--grep: {error}")

    command: List[str] = list(args.command)
    if command[:1] == ["--"]:
        command = command[1:]
    if not command:
        parser.print_help()
        return 2

    if command[0] == "errors":
        return run_errors(parser, command[1:], opts)

    if command[0] in OWN_COMMANDS and len(command) > 1 and command[0] != "shell-init":
        # `dvt clean --keep 5`: options after dvt's own commands are dvt's.
        before = list(argv)[:len(argv) - len(args.command)]
        return run(before + command[1:] + [command[0]])

    if command[0] == "clean":
        return clean.run(["docker"], opts)
    if command[0] == "doctor":
        return doctor.run(["docker"], opts)
    if command[0] == "dash":
        frame = lambda width: dashboard.frame(opts, width)  # noqa: E731
        if opts.watch:
            return live.run(frame, "dvt dash", opts.interval)
        sys.stdout.write(frame(opts.width))
        return 0

    if command[0] == "shell-init":
        return shell_init(command[1:])

    command = docker.expand_shortcut(command)

    if args.raw:
        return passthrough(command)

    if not docker.is_docker(command):
        return run_table(command, opts)

    kind = docker.classify(command).name
    if kind == "logs":
        return logs.run(command, opts)
    if kind == "inspect":
        return inspect.run(command, opts)
    if kind == "stats":
        live_stats = not opts.once and sys.stdout.isatty() and "--no-stream" not in command
        if live_stats or opts.watch:
            return live.run(tables.snapshot(command, opts), " ".join(command), opts.interval)
        return tables.run(command, opts)
    if kind == "table" and images.is_image_list(command):
        if "--group" in command:  # also accepted after the command
            command = [a for a in command if a != "--group"]
            opts.group = True
        if opts.group:
            return images.run_group(command, opts)
    if kind == "table":
        return run_table(command, opts)
    return passthrough(command)


def run_errors(parser: argparse.ArgumentParser, rest: List[str], opts: Options) -> int:
    """`dvt errors [TARGET...]`: targets and options can be mixed freely."""
    sub = argparse.ArgumentParser(prog="dvt errors", description=errors.__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    sub.add_argument("targets", nargs="*", metavar="NAME",
                     help="stack, service or container name or ID (default: everything)")
    sub.add_argument("--since", metavar="TIME",
                     help=f"30m, 6h, 2d, 1w or a date (default: {errors.DEFAULT_SINCE})")
    sub.add_argument("--grep", metavar="REGEX", help="count only lines matching this")
    sub.add_argument("--full", action="store_true", help="show every kind of message")
    sub.add_argument("--width", type=int, help="table width")
    sub.add_argument("--no-color", action="store_true", help="disable colors")
    sub.add_argument("--color", action="store_true", help="force colors")
    args = sub.parse_intermixed_args(rest)

    if args.since:
        opts.since = args.since
    if args.grep:
        try:
            opts.grep = re.compile(args.grep, re.IGNORECASE)
        except re.error as error:
            sub.error(f"--grep: {error}")
    opts.full = opts.full or args.full
    opts.width = args.width or opts.width
    if args.no_color:
        colors.enabled = False
    elif args.color:
        colors.enabled = True
    return errors.run(["docker"], args.targets, opts)


def run_table(command: List[str], opts: Options) -> int:
    if opts.watch:
        return live.run(tables.snapshot(command, opts), " ".join(command), opts.interval)
    return tables.run(command, opts)


def shell_init(rest: List[str]) -> int:
    name: Optional[str] = rest[0] if rest else None
    if name is None:
        sys.stdout.write(shell.USAGE)
        return 0
    if name not in shell.SCRIPTS:
        sys.stderr.write(f"dvt: unsupported shell '{name}' (bash, zsh, fish)\n")
        return 2
    sys.stdout.write(shell.script(name))
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    try:
        return run(sys.argv[1:] if argv is None else argv)
    except KeyboardInterrupt:
        return 130
    except BrokenPipeError:
        # Output piped into `head` or `less` that quit early.
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
