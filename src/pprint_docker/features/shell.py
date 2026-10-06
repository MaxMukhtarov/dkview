"""`pprint shell-init`: make plain `docker ...` go through pprint."""

from __future__ import annotations

POSIX = """\
# pprint: format docker output when printing to a terminal.
# Scripts and pipes (docker ps | grep ...) still get docker's raw output.
# Use `command docker ...` to bypass it once.
docker() {
    if [ -t 1 ]; then
        command pprint docker "$@"
    else
        command docker "$@"
    fi
}
"""

FISH = """\
# pprint: format docker output when printing to a terminal.
function docker --wraps docker
    if isatty stdout
        command pprint docker $argv
    else
        command docker $argv
    end
end
"""

SCRIPTS = {"bash": POSIX, "zsh": POSIX, "sh": POSIX, "fish": FISH}

USAGE = """\
Add one of these to your shell's startup file, then open a new terminal:

  bash:  echo 'eval "$(pprint shell-init bash)"' >> ~/.bashrc
  zsh:   echo 'eval "$(pprint shell-init zsh)"' >> ~/.zshrc
  fish:  echo 'pprint shell-init fish | source' >> ~/.config/fish/config.fish
"""


def script(shell: str) -> str:
    return SCRIPTS[shell]
