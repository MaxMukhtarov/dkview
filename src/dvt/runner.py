"""Running commands, either captured for formatting or attached to the terminal."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from typing import Sequence


@dataclass
class Result:
    code: int
    stdout: str
    stderr: str


def capture(argv: Sequence[str]) -> Result:
    try:
        process = subprocess.run(
            list(argv),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            errors="replace",
        )
        return Result(process.returncode, process.stdout, process.stderr)
    except FileNotFoundError:
        return Result(127, "", f"{argv[0]}: command not found\n")


def passthrough(argv: Sequence[str]) -> int:
    """Run a command attached to the terminal, exactly as if typed directly."""
    try:
        process = subprocess.Popen(list(argv))
    except FileNotFoundError:
        sys.stderr.write(f"{argv[0]}: command not found\n")
        return 127
    while True:
        try:
            return process.wait()
        except KeyboardInterrupt:
            # Ctrl+C reaches the child too; let it exit on its own terms.
            continue
