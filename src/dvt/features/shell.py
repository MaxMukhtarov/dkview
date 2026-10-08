"""`dvt shell-init`: make plain `docker ...` go through dvt."""

from __future__ import annotations

POSIX = """\
# dvt: format docker output when printing to a terminal.
# Scripts and pipes (docker ps | grep ...) still get docker's raw output.
# Use `command docker ...` to bypass it once.
docker() {
    if [ -t 1 ]; then
        command dvt docker "$@"
    else
        command docker "$@"
    fi
}
"""

FISH = """\
# dvt: format docker output when printing to a terminal.
function docker --wraps docker
    if isatty stdout
        command dvt docker $argv
    else
        command docker $argv
    end
end
"""

SCRIPTS = {"bash": POSIX, "zsh": POSIX, "sh": POSIX, "fish": FISH}

USAGE = """\
Add one of these to your shell's startup file, then open a new terminal:

  bash:  echo 'eval "$(dvt shell-init bash)"' >> ~/.bashrc
  zsh:   echo 'eval "$(dvt shell-init zsh)"' >> ~/.zshrc
  fish:  echo 'dvt shell-init fish | source' >> ~/.config/fish/config.fish
"""


def script(shell: str) -> str:
    return SCRIPTS[shell]
