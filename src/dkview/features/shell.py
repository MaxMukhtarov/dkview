from __future__ import annotations

POSIX = """\
# dkview: format docker output when printing to a terminal.
docker() {
    if [ -t 1 ]; then
        command dkview docker "$@"
    else
        command docker "$@"
    fi
}
"""

FISH = """\
# dkview: format docker output when printing to a terminal.
function docker --wraps docker
    if isatty stdout
        command dkview docker $argv
    else
        command docker $argv
    end
end
"""

POWERSHELL = """\
# dkview: format docker output when printing to a terminal.
function docker {
    $real = Get-Command docker -CommandType Application | Select-Object -First 1
    if ([Console]::IsOutputRedirected) { & $real @args } else { dkview docker @args }
}
"""

SCRIPTS = {"bash": POSIX, "zsh": POSIX, "sh": POSIX, "fish": FISH,
           "powershell": POWERSHELL, "pwsh": POWERSHELL}

USAGE = """\
Add one of these to your shell's startup file, then open a new terminal:

  bash:  echo 'eval "$(dkview shell-init bash)"' >> ~/.bashrc
  zsh:   echo 'eval "$(dkview shell-init zsh)"' >> ~/.zshrc
  fish:  echo 'dkview shell-init fish | source' >> ~/.config/fish/config.fish
  PowerShell (Windows):
         Add-Content $PROFILE 'Invoke-Expression (dkview shell-init powershell | Out-String)'
"""


def script(shell: str) -> str:
    return SCRIPTS[shell]
