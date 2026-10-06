# pprint

Readable, colored output for docker commands. Run any docker command
through `pprint` and list commands come back as clean, width-fitted
tables. Everything else (`run`, `exec`, `build`, typos) behaves exactly
like plain docker.

```
$ pprint ps
┌──────────────┬──────────────────┬────────────────┬─────────┬───────────────────┬──────────────────────┬────────┐
│ CONTAINER ID │ IMAGE            │ COMMAND        │ CREATED │ STATUS            │ PORTS                │ NAMES  │
├──────────────┼──────────────────┼────────────────┼─────────┼───────────────────┼──────────────────────┼────────┤
│ 482fda92e935 │ alpine           │ "sleep 100000" │ 7m ago  │ Up 7m (unhealthy) │                      │ sick   │
│ a60bbdb5f70a │ alpine           │ "sleep 100000" │ 7m ago  │ Up 7m (healthy)   │ 0.0.0.0:8080->80/tcp │ web    │
└──────────────┴──────────────────┴────────────────┴─────────┴───────────────────┴──────────────────────┴────────┘
```

## Install

Needs Python 3.7 or newer and nothing else.

**Single file (easiest for servers):**

```sh
make zipapp                       # builds dist/pprint
scp dist/pprint server:~/bin/pprint
ssh server chmod +x ~/bin/pprint     # or run it as: python3 ~/bin/pprint ps
```

**With pip:**

```sh
pip install --user .              # installs the `pprint` and `dpp` commands
```

## What it does

| Command | What you get |
| --- | --- |
| `pprint ps`, `images`, `service ls`, `service ps`, `node ls`, `volume ls`, `network ls`, `stack ps`, `system df`, `compose ps`, ... | A boxed table. Long values wrap at `/ : -` instead of being cut, and short columns keep their full width. |
| `pprint stats` | A live view that refreshes in place, like `top` (Ctrl+C quits). `--once` prints a single snapshot. |
| `pprint inspect web` | A short summary of a container, image or service: status, health, ports, networks, mounts, env, labels. `--full` shows every field as a colored tree. |
| `pprint logs -f web` | Log lines colored by level (errors red, warnings yellow), stderr included. Add `--grep` to filter. |
| `pprint dash` | One screen with host info, anything that needs attention, containers with CPU and memory, services and disk use. `--watch` keeps it live. |
| anything else | Runs untouched, exactly like docker. |

The word `docker` is optional: `pprint ps -a` is the same as `pprint docker ps -a`.

### Colors

* **STATUS**: green when up or healthy, yellow while starting or restarting, red for unhealthy or a non-zero exit, grey for a clean exit.
* **REPLICAS**: green when all are running, yellow when some are, red when none are.
* **CURRENT STATE** (service ps): green when running, red when failed or rejected.
* **CPU % / MEM %**: yellow from 50%, red from 80%.

Colors switch off automatically when output goes to a pipe or file, or when `NO_COLOR` is set.

## Options

pprint's options go **before** the command.

```
--cols A,B,...     show only these columns, in this order: --cols name,status,ports
                   (names can be shortened: cpu, mem, img, id)
--sort COL         sort by a column; numbers, sizes, percentages and ages sort by value
--desc             largest first
--grep REGEX       keep matching rows or log lines (case-insensitive)
--short            hide the registry host in image names
--long-times       keep "4 minutes ago" instead of "4m ago"
--trunc            keep docker's own truncation instead of full values
--width N          table width (default: terminal width)
-w, --watch        redraw every few seconds until Ctrl+C
-n, --interval S   seconds between redraws (default 2)
--once             docker stats: one snapshot, not a live view
--full             inspect: every field as a tree
--raw              run the command untouched
--no-color / --color
```

Examples:

```sh
pprint --sort cpu --desc stats                  # busiest containers first, live
pprint --short --cols name,status,image ps -a   # compact container list
pprint --watch service ls                       # watch a deploy roll out
pprint --grep 'timeout|refused' logs -f api     # only the interesting lines
pprint inspect web                              # what is this container doing?
pprint dash --watch                             # host overview, live
```

Set defaults you always want in `PPRINT_OPTS`:

```sh
export PPRINT_OPTS="--short"
```

## Use it for plain `docker` too

```sh
echo 'eval "$(pprint shell-init bash)"' >> ~/.bashrc    # or zsh
echo 'pprint shell-init fish | source' >> ~/.config/fish/config.fish
```

After that, `docker ps` in your terminal is formatted automatically. When
docker's output goes to a pipe or a script (`docker ps | grep x`), it is
left untouched, so nothing that parses docker output breaks. Run
`command docker ...` to skip pprint once.

## Development

```
src/pprint_docker/
  cli.py          command line and dispatch to features
  docker.py       recognising docker commands, which ones print tables
  table.py        Table model, parsing aligned command output
  layout.py       width fitting, wrapping and drawing the box table
  transform.py    shorter values, column choice, sorting, filtering
  styles.py       which cells get which color
  ansi.py         color codes and escape-aware text measuring
  runner.py       capturing or passing through a command
  options.py      settings shared by all features
  features/
    tables.py     list commands as tables
    live.py       full-screen redraw loop (stats, --watch, dash --watch)
    logs.py       log coloring and --grep
    inspect.py    inspect summaries and JSON tree
    dashboard.py  pprint dash
    shell.py      pprint shell-init
tests/            pytest suite; uses recorded docker output, no daemon needed
```

```sh
make test      # run the tests
make zipapp    # build dist/pprint
make build     # build a wheel (needs `pip install build`)
```

Commands pprint does not recognise as tables are never captured, so
streaming commands like `logs -f`, `events` or `run -it` cannot hang it.
For non-docker commands pprint still tries to format the output as a
table, so use it there only with commands that finish on their own.
