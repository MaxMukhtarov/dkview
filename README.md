# pprint

**Readable, colored output for docker commands.**

`pprint` runs a docker command for you and turns its output into a clean,
width-fitted, colored table. Problems stand out at a glance: unhealthy
containers are red, services missing replicas are red, busy CPUs are yellow.
Commands that are not tables (`run`, `exec`, `build`, `logs -f`, typos...)
behave exactly like plain docker.

```
$ pprint service ls
┌──────────────┬────────┬────────────┬──────────┬────────────────────────┬────────────────┐
│ ID           │ NAME   │ MODE       │ REPLICAS │ IMAGE                  │ PORTS          │
├──────────────┼────────┼────────────┼──────────┼────────────────────────┼────────────────┤
│ mgca4i2paztn │ api    │ replicated │ 2/2      │ alpine:latest          │ *:9000->80/tcp │   <- green
│ o1cs5dpu3fsr │ broken │ replicated │ 0/1      │ alpine:nonexistent-tag │                │   <- red
└──────────────┴────────┴────────────┴──────────┴────────────────────────┴────────────────┘
```

* Repository: https://github.com/MaxMukhtarov/pprint-docker (branch `feature`)
* Version: 2.4.0
* Needs: Python 3.7 or newer and the docker CLI. No other packages, no internet.

---

## Contents

1. [Install](#1-install)
2. [Check that it works](#2-check-that-it-works)
3. [Quick start](#3-quick-start)
4. [Commands](#4-commands)
5. [Options](#5-options)
6. [Colors](#6-colors)
7. [Make plain `docker` use pprint](#7-make-plain-docker-use-pprint)
8. [Default options](#8-default-options)
9. [Update](#9-update)
10. [Uninstall](#10-uninstall)
11. [Troubleshooting](#11-troubleshooting)
12. [FAQ](#12-faq)
13. [Development](#13-development)

---

## 1. Install

Pick **one** of the methods below. Method A is the one to use on servers
without internet access.

Before you start, check Python:

```sh
python3 --version        # must be 3.7 or newer
```

### A. From the source archive, no internet needed (recommended for servers)

Copy `pprint-source.tar.gz` (or `pprint-source.zip`) to the server, then:

```sh
# 1. Unpack into your home folder. This creates ~/pprint
tar -xzf pprint-source.tar.gz -C ~
#   or, for the zip (no unzip command needed):
#   python3 -m zipfile -e pprint-source.zip ~

# 2. Create the `pprint` command
mkdir -p ~/bin
cat > ~/bin/pprint <<'EOF'
#!/bin/sh
PYTHONPATH="$HOME/pprint/src" exec python3 -m pprint_docker "$@"
EOF
chmod +x ~/bin/pprint

# 3. Make sure ~/bin is on your PATH (already true on RHEL/CentOS)
echo "$PATH" | tr ':' '\n' | grep -qx "$HOME/bin" \
  || { echo 'export PATH="$HOME/bin:$PATH"' >> ~/.bashrc; export PATH="$HOME/bin:$PATH"; }
hash -r
```

To install it for **every user** on the machine, unpack it into `/opt`
and put the command in `/usr/local/bin` instead:

```sh
sudo tar -xzf pprint-source.tar.gz -C /opt
sudo tee /usr/local/bin/pprint >/dev/null <<'EOF'
#!/bin/sh
PYTHONPATH="/opt/pprint/src" exec python3 -m pprint_docker "$@"
EOF
sudo chmod +x /usr/local/bin/pprint
```

### B. From GitHub (machines with access to GitHub)

```sh
git clone -b feature https://github.com/MaxMukhtarov/pprint-docker.git ~/pprint
```

Then do step 2 of method A to create the `~/bin/pprint` command.

### C. With pip

```sh
cd ~/pprint
python3 -m pip install --user .
```

This installs two commands into `~/.local/bin`: `pprint` and the short
alias `dpp`. Make sure `~/.local/bin` is on your PATH.

### D. As one single file

On a machine that has `make` and the source:

```sh
cd ~/pprint
make zipapp                      # builds dist/pprint
```

`dist/pprint` is a compressed archive of the code that Python runs
directly. Copy it anywhere, `chmod +x` it, and run it. You can't read the
code inside it, but `unzip -l dist/pprint` lists what it contains.

---

## 2. Check that it works

```sh
type pprint            # should point to ~/bin/pprint (or your chosen path)
pprint --version       # pprint 2.4.0
pprint ps              # your containers as a table
```

If `type pprint` shows an old alias such as
`alias pprint='python3 ~/pprint.py'`, delete that line from `~/.bashrc`,
then open a new terminal. Also delete any old `pprint.py` file, because a
file with that name breaks Python's own `pprint` module.

---

## 3. Quick start

```sh
pprint ps -a                          # all containers
pprint service ls                     # swarm services, replicas colored
pprint stats                          # live CPU/memory view, Ctrl+C to quit
pprint inspect <container>            # short summary of one container
pprint logs -f <container>            # colored logs
pprint dash                           # one-screen overview of the host
pprint images --group                 # one row per repository, with sizes
pprint clean --dry-run                # old unused image tags you could remove
pprint doctor                         # what is wrong with failing services
pprint errors                         # errors and warnings in all logs, last 30 minutes
pprint errors transfers --since 2d    # the same for one stack, service or container
```

The word `docker` is optional: `pprint ps -a` and `pprint docker ps -a`
are the same.

---

## 4. Commands

### 4.1 Tables

These docker commands are shown as tables:

| Area | Commands |
| --- | --- |
| Containers | `ps`, `container ls`, `top`, `stats` |
| Images | `images`, `image ls`, `history`, `image history`, `search` |
| Swarm | `service ls`, `service ps`, `node ls`, `node ps`, `stack ls`, `stack ps`, `stack services`, `secret ls`, `config ls` |
| Other | `volume ls`, `network ls`, `system df`, `context ls`, `plugin ls`, `buildx ls` |
| Compose | `compose ps`, `compose ls`, `compose images`, `compose top`, `compose stats` |

Examples:

```sh
pprint ps -a
pprint ps --filter status=exited
pprint images
pprint service ps api
pprint node ls
pprint system df
pprint compose -f docker-compose.prod.yml ps
```

What pprint does to tables:

* **Nothing is cut off.** For commands that support it, pprint asks
  docker for full values (`--no-trunc`) so COMMAND, ERROR and similar
  columns aren't shortened with `…`. Long values wrap inside their cell
  instead, breaking after `/ : - _ .` rather than mid-word.
* **IDs stay short.** Full 64-character IDs and image digests
  (`@sha256:...`) are trimmed back to what docker normally shows.
* **Short columns keep their width.** CREATED, STATUS and PORTS never get
  squeezed. Only long columns such as IMAGE, COMMAND and NAMES wrap.
* **Ages are compact.** `4 minutes ago` becomes `4m ago` and
  `Up About an hour` becomes `Up 1h`. Use `--long-times` to keep the
  originals.
* **Empty cells stay empty.** A container with no ports shows an empty
  PORTS cell, and nothing shifts into the wrong column.

* **Images in use are marked.** In `images` and `image ls`, a green `●`
  before the name means at least one container (running or stopped) uses
  that image. A grey `○` means none does, so it's safe to remove. A legend
  is printed under the table.

  ```
  $ pprint --short images
  ┌────────────────────────────────────┬─────────────────────────────────────┬──────────────┬─────────┬────────┐
  │ REPOSITORY                         │ TAG                                 │ IMAGE ID     │ CREATED │ SIZE   │
  ├────────────────────────────────────┼─────────────────────────────────────┼──────────────┼─────────┼────────┤
  │ ● doublewave/transfers/api-v2      │ dev-e55edc11695bf0e572164ed49ea7a64 │ 3a4e72375f57 │ 32h ago │ 432MB  │
  │                                    │ 0b3a1b434                           │              │         │        │
  │ ○ doublewave/transfers/backoffice/ │ testing-49033ae06da069bca7aacb7ffef │ d8bcc442c9ec │ 2w ago  │ 80.1MB │
  │   ui                               │ 703cd0366dfe0                       │              │         │        │
  └────────────────────────────────────┴─────────────────────────────────────┴──────────────┴─────────┴────────┘
  ● used by a container   ○ not used
  ```

  To list only the unused ones: `pprint --grep ○ images`.

Example:

```
$ pprint --short --cols name,status,image ps -a
┌──────────────────────────────────────────┬───────────────────┬───────────────┐
│ NAMES                                    │ STATUS            │ IMAGE         │
├──────────────────────────────────────────┼───────────────────┼───────────────┤
│ sick                                     │ Up 7m (unhealthy) │ alpine        │   <- red
│ oneshot                                  │ Exited (1) 7m ago │ alpine        │   <- red
│ web                                      │ Up 7m (healthy)   │ alpine        │   <- green
└──────────────────────────────────────────┴───────────────────┴───────────────┘
```

### 4.2 Live stats

```sh
pprint stats                      # live view, refreshes every 2 seconds
pprint --sort cpu --desc stats    # busiest containers at the top
pprint -n 5 stats                 # refresh every 5 seconds
pprint --once stats               # print one snapshot and exit
```

Plain `docker stats` never exits, so pprint takes one sample at a time
(`--no-stream`) and redraws the screen in place, like `top`. Press
**Ctrl+C** to quit. When the output goes to a file or a pipe, pprint
prints a single snapshot instead.

### 4.3 Watch any table

```sh
pprint --watch service ls         # watch a deploy roll out
pprint --watch ps -a
pprint -w -n 1 service ps api     # every second
```

### 4.4 inspect

```sh
pprint inspect web                # summary of a container
pprint inspect web db cache       # several at once
pprint image inspect alpine       # summary of an image
pprint service inspect api        # summary of a swarm service
pprint --full inspect web         # every field, as a colored tree
```

The summary shows what you usually look for:

```
web  container
  ID              a60bbdb5f70a
  Image           alpine
  Status          running (healthy)
  Started         8m ago
  Restarts        0
  Restart policy  no
  Command         sleep 100000

Ports  (1)
  0.0.0.0:8080  → 80/tcp

Networks  (1)
  bridge  172.17.0.2

Environment  (1)
  PATH  /usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
```

For an unhealthy container the summary also shows the output of the last
failed health check. Other objects (networks, volumes, nodes...) are shown
as a tree. Use `--format` to get docker's raw output, for example
`pprint inspect --format '{{.State.Status}}' web`.

### 4.5 Logs

```sh
pprint logs web                           # all logs, colored
pprint logs -f --tail 100 web             # follow, last 100 lines
pprint --grep error logs web              # only lines matching "error"
pprint --grep 'timeout|refused' logs -f api
pprint service logs -f api                # swarm service logs
pprint compose logs -f                    # compose logs, one color per service
```

* Lines with ERROR, FATAL, PANIC or FAIL are red, WARN lines are yellow,
  INFO is marked green and DEBUG/TRACE are dimmed. JSON logs
  (`"level":"error"`) and `level=warn` styles are recognised too.
* Leading timestamps are dimmed so the message stands out.
* The container's stderr is included, so error output isn't lost.
* `--grep` matches are highlighted.
* Ctrl+C stops following.

### 4.6 Dashboard

```sh
pprint dash               # one snapshot
pprint dash --watch       # live, refreshes every 2 seconds
pprint --short dash       # without registry hosts in image names
```

```
Docker 29.8.2 on vm · 4 CPUs · 15.7GiB RAM · swarm active
Containers: 5 running · 1 unhealthy · 1 failed

Needs attention (3)
  ✗ container sick: Up 8m (unhealthy)
  ✗ container oneshot: Exited (1) 8m ago
  ✗ service broken: 0/1 replicas running

Containers
┌─────────┬───────────────────┬────────┬───────┬─────────┬───────────────┐
│ NAME    │ STATUS            │ IMAGE  │ CPU % │ MEM     │ PORTS         │
...
Services
...
Disk
...
```

Problem containers are listed first. When nothing is wrong, the
"Needs attention" list is replaced by a green
"✓ Everything is running and healthy". The Services section only appears
on swarm managers.

### 4.7 Images grouped by repository

```sh
pprint images --group                 # one row per repository
pprint --short images --group         # without the registry host
pprint --grep backoffice images --group
```

Instead of one row per tag, you get one row per repository, biggest first:

```
┌───────────────────────┬──────┬──────────────────────┬────────┬────────┬────────────┬─────────────┐
│ REPOSITORY            │ TAGS │ NEWEST TAG           │ NEWEST │ IN USE │ TOTAL SIZE │ UNUSED SIZE │
├───────────────────────┼──────┼──────────────────────┼────────┼────────┼────────────┼─────────────┤
│ ● doublewave/         │ 4    │ dev-                 │ 1d ago │ 3 of 4 │ 1.75GB     │ 431MB       │
│                       │      │ e55edc11695bf0e57    │        │        │            │             │
│ transfers/api-v2      │      │ 2164ed49ea7a640b3a1b │        │        │            │             │
│                       │      │ 4                    │        │        │            │             │
│                       │      │ 34                   │        │        │            │             │
│ ● doublewave/         │ 4    │ testing-             │ 4h ago │ 1 of 4 │ 1.12GB     │ 843MB       │
│                       │      │ c5cbfead923c7        │        │        │            │             │
│ transfers/            │      │ ff776d60ec52225bff24 │        │        │            │             │
│                       │      │ 6                    │        │        │            │             │
│ backoffice/api        │      │ 9235ef               │        │        │            │             │
│ ● doublewave/devops/  │ 1    │ v3.7.13              │ 4w ago │ 1 of 1 │ 252MB      │             │
│   registry/traefik/   │      │                      │        │        │            │             │
│   traefik             │      │                      │        │        │            │             │
│ ● doublewave/         │ 2    │ testing-             │ 1d ago │ 1 of 2 │ 160MB      │ 80.1MB      │
│                       │      │ bd55266b6d414        │        │        │            │             │
│ transfers/            │      │ fb51488f2853f0266b69 │        │        │            │             │
│                       │      │ 0                    │        │        │            │             │
│ backoffice/ui         │      │ e37b8c               │        │        │            │             │
└───────────────────────┴──────┴──────────────────────┴────────┴────────┴────────────┴─────────────┘
● used by a container   ○ not used
11 images in 5 repositories, 3.28GB in total, 1.35GB not used
```

* **TAGS**: how many tags the repository has.
* **NEWEST TAG / NEWEST**: the most recently built tag and how old it is.
* **IN USE**: how many of those tags a container uses, running or stopped.
* **TOTAL SIZE / UNUSED SIZE**: an image with several tags is counted
  once. Images share layers, so the disk space you actually get back can
  be smaller than UNUSED SIZE.

`--group` can go before or after `images`. `--sort` and `--cols` work on
the grouped table too, for example `pprint --sort unused --desc images --group`.

### 4.8 Clean up old images: `pprint clean`

```sh
pprint clean --dry-run          # only show what would be deleted
pprint clean                    # show the plan, then ask before deleting
pprint clean --keep 2           # keep only the newest 2 tags per repository
pprint clean --keep 5           # keep the newest 5 tags per repository
pprint clean --grep api-v2      # only look at matching repositories
pprint clean --yes              # delete without asking (for cron jobs)
```

How pprint decides what to delete, per repository:

1. The newest **N** tags are always kept (`--keep N`, default **3**).
2. Any image used by a container, **running or stopped**, is always kept.
3. Every other tag is deleted. Unused dangling images (`<none>`) are
   deleted too.

It prints the plan first:

```
┌───────────────────────────┬────────────────────────────┬──────────────┬─────────┬───────┬────────┐
│ REPOSITORY                │ TAG                        │ IMAGE ID     │ CREATED │ SIZE  │ ACTION │
├───────────────────────────┼────────────────────────────┼──────────────┼─────────┼───────┼────────┤
│ ○ doublewave/transfers/   │ testing-42095844d514a1f1da │ 4bbfa42b6f2c │ 1w ago  │ 281MB │ delete │
│   backoffice/api          │ 0572dc0424de4f3b0484f0     │              │         │       │        │
│ ○ doublewave/transfers/   │ testing-9792faf89378ea4aae │ 44939f22ce0c │ 2w ago  │ 281MB │ delete │
│   backoffice/api          │ f1f336dd4bafcda106378c     │              │         │       │        │
│ ○ doublewave/transfers/   │ dev-f2241ba4d16b49ec25c17d │ 78cc88c49346 │ 2d ago  │ 431MB │ delete │
│   api-v2                  │ 42c92ff7fa1fa561f6         │              │         │       │        │
└───────────────────────────┴────────────────────────────┴──────────────┴─────────┴───────┴────────┘
3 images to delete in 2 repositories, up to 993MB freed  (keeping the newest 2 per repository and every image a container uses)
Delete these 3 images? [y/N]
```

* Nothing is deleted until you answer `y`. Any other answer, or Enter,
  cancels.
* `--dry-run` also lists the tags being kept and why, then stops.
* Without a terminal (in a script or cron job), pprint refuses to delete
  unless you pass `--yes`.
* Images are removed one at a time with `docker rmi repo:tag`, so one
  failure doesn't stop the rest. Each result is printed.
* Removing a tag whose image is also tagged elsewhere only removes that
  tag, and the image stays. The "freed" estimate accounts for that.
* Containers, volumes and networks are never touched. For those, use
  docker's own `docker container prune`, `docker volume prune` and
  `docker network prune`.

### 4.9 Swarm doctor: `pprint doctor`

```sh
pprint doctor                   # check every swarm service
pprint doctor --full            # list every failed task instead of grouping
pprint doctor --grep api        # only matching services
```

For each service that isn't healthy, you get the replicas, the current
state, the full error text grouped by message with a count, and a hint
about the likely cause:

```
Swarm services: 12 healthy · 1 restarting · 1 failing

✗ broken  0/1 replicas · alpine:nonexistent-tag
  5 failed tasks in recent history · now: Rejected 2s ago
  ┌───────┬──────────┬────────┬───────┬──────────────────────────────────────────────────────┐
  │ TIMES │ STATE    │ LAST   │ NODES │ ERROR                                                │
  ├───────┼──────────┼────────┼───────┼──────────────────────────────────────────────────────┤
  │ 5×    │ Rejected │ 2s ago │ vm    │ failed to resolve reference "docker.io/library/      │
  │       │          │        │       │ alpine:nonexistent-tag": not found                   │
  └───────┴──────────┴────────┴───────┴──────────────────────────────────────────────────────┘
  → The image can't be pulled. Check the image name and tag, and that the node can
    log in to the registry (deploy with --with-registry-auth).

! crashy  1/1 replicas · busybox:latest
  4 failed tasks in recent history · now: Running 10s ago
  ...
  → The program inside the container exited with an error. See why with
    `pprint errors crashy`.

✓ Healthy
┌──────────┬──────────┬──────────────────────────────┐
│ SERVICE  │ REPLICAS │ IMAGE                        │
...
```

* **✗ red**: fewer replicas are running than wanted.
* **! yellow**: all replicas are running, but tasks failed recently (a
  restart loop), or an update is paused or rolling back.
* **✓ green**: all replicas are running with no recent failures.

Hints cover the common causes: images that can't be pulled, non-zero
exits, exit 137 (out of memory or killed), no suitable node, ports already
in use, missing mounts and failing health checks.

Docker keeps only the last few tasks of each service (5 per replica by
default), so "failed tasks in recent history" counts those. `pprint doctor`
exits with code 1 when any service is failing, so it can be used in
scripts and monitoring checks.

### 4.10 Errors in logs: `pprint errors`

Reads the logs and tells you what is breaking: errors and warnings are
counted, and repeats of the same message are grouped, with how often it
happened and when it was first and last seen.

```sh
pprint errors                         # every service and container, last 30 minutes
pprint errors transfers               # one stack (all of its services)
pprint errors transfers_api           # one service
pprint errors payments                # one container, by name
pprint errors 9a8b7c --since 2d       # one container, by ID, last 2 days
pprint errors transfers payments      # several at once
pprint errors api --grep timeout      # count only lines matching a pattern
pprint errors --full                  # every kind of message, not just the top 10
```

Example:

```
$ pprint errors
Errors and warnings, last 30m: 7 errors · 1 warning in 2 of 5 sources
┌───────────────┬───────────┬────────┬──────────┬────────────┬───────┐
│ SOURCE        │ KIND      │ ERRORS │ WARNINGS │ LAST ERROR │ LINES │
├───────────────┼───────────┼────────┼──────────┼────────────┼───────┤
│ transfers_api │ service   │ 4      │ 1        │ 4m ago     │ 7     │
│ payments      │ container │ 3      │ 0        │ 4m ago     │ 5     │
└───────────────┴───────────┴────────┴──────────┴────────────┴───────┘
✓ nothing in quiet-box, traefik, transfers_worker

✗ transfers_api  service · 4 errors · 1 warning · 3 different messages
  ┌───────┬───────┬────────┬────────┬──────────────────────────────────────────────────────────┐
  │ COUNT │ LEVEL │ LAST   │ FIRST  │ MESSAGE                                                  │
  ├───────┼───────┼────────┼────────┼──────────────────────────────────────────────────────────┤
  │ 3×    │ error │ 4m ago │ 4m ago │ ERROR Timeout calling http://10.0.3.2:8080/accounts      │
  │       │       │        │        │ after 30000ms (order 9)                                  │
  │ 1×    │ error │ 4m ago │ 4m ago │ ERROR Npgsql.NpgsqlException: connection refused         │
  │ 1×    │ warn  │ 4m ago │ 4m ago │ WARN Retrying payment 5, attempt 2                       │
  └───────┴───────┴────────┴────────┴──────────────────────────────────────────────────────────┘

✗ payments  container · 3 errors · 2 different messages
  ┌───────┬───────┬────────┬────────┬──────────────────────────────────────────────────────────┐
  │ COUNT │ LEVEL │ LAST   │ FIRST  │ MESSAGE                                                  │
  ├───────┼───────┼────────┼────────┼──────────────────────────────────────────────────────────┤
  │ 2×    │ error │ 4m ago │ 4m ago │ fail: Payments.Api.Controllers[0] Unhandled exception    │
  │       │       │        │        │ for request 4f3a194-9c:                                  │
  │       │       │        │        │ System.InvalidOperationException: Sequence contains no   │
  │       │       │        │        │ elements                                                 │
  │ 1×    │ error │ 4m ago │ 4m ago │ System.TimeoutException: The operation has timed out     │
  └───────┴───────┴────────┴────────┴──────────────────────────────────────────────────────────┘
```

**What to pass.** Each name can be a stack, a service or a container, by
name or ID (an ID can be shortened, like docker allows). pprint works out
which it is. If a stack and a service have the same name, the stack wins.
With no name, it reads every swarm service plus every container that
isn't part of a service. A service's own task containers are skipped,
because the service logs already contain them.

**`--since`.** How far back to read: `30m` (the default), `6h`, `2d`, `1w`,
`1h30m`, or a date and time like `2026-10-07T09:00`. Days and weeks work
even though docker itself only understands hours.

**What counts as an error or warning.** Lines with a level word, such as
`ERROR`, `FATAL`, `CRITICAL`, `fail:` (.NET), `level=error` and
`"level":"error"`, and the same for `WARN`/`warning`. Lines without a level
that report an exception (`System.TimeoutException: ...`, a Python
`Traceback`, a Go `panic:`) count as errors too. The stack trace lines
below an error (`   at ...`) aren't counted separately.

**How repeats are grouped.** Numbers, IDs, IPs, hashes and timestamps are
ignored when comparing messages, so `Timeout calling 10.0.3.3 (order 3)` and
`Timeout calling 10.0.3.6 (order 6)` are the same problem. The table shows
the most recent example.

**In scripts and cron.** `pprint errors` exits with code 1 when it finds
any error, 0 when there are none (warnings alone give 0), and 2 when a
name doesn't exist or `--since` is invalid. For example:

```sh
pprint --no-color errors transfers --since 1h > /tmp/errors.txt || mail -s "transfers errors" ops@doublewave.uz < /tmp/errors.txt
```

Reading a long window over many containers can take a while, because
docker has to send all of those log lines. Narrow it with a name or a
shorter `--since`.

### 4.11 Everything else

Any command that isn't a table, logs or inspect runs exactly as if you'd
typed it without `pprint`. That includes `run`, `exec -it`, `build`,
`pull`, `events`, `login`, `--help` and typos. Their output, errors,
exit codes and Ctrl+C all behave normally.

```sh
pprint exec -it web sh      # works normally
pprint --raw ps             # force plain docker output for a table command
```

### 4.12 Non-docker commands

pprint also tries to format other column-aligned output, such as
`pprint kubectl get pods`. If the output isn't a table, it's printed
unchanged. pprint waits for these commands to finish, so only use it with
commands that end on their own.

---

## 5. Options

pprint's own options go **before** the command:
`pprint --sort cpu stats`, not `pprint stats --sort cpu`.
(Options after the command are passed to docker.)

### Table view

| Option | What it does | Example |
| --- | --- | --- |
| `--cols A,B,...` | Show only these columns, in this order. Names can be shortened or abbreviated (`cpu`, `mem`, `img`, `id`, `stat`). | `pprint --cols name,status,ports ps` |
| `--sort COL` | Sort rows by a column. Numbers, sizes (`512MiB`), percentages and ages sort by value. | `pprint --sort created images` |
| `--desc` | Sort largest first. | `pprint --sort cpu --desc stats` |
| `--grep REGEX` | Keep only rows (or log lines) matching, case-insensitive. | `pprint --grep api ps` |
| `--short` | Hide the registry host in image names (`registry.example.uz/team/api:v1` → `team/api:v1`). | `pprint --short ps` |
| `--long-times` | Keep `4 minutes ago` instead of `4m ago`. | `pprint --long-times ps` |
| `--trunc` | Let docker truncate values as it normally does. | `pprint --trunc ps` |
| `--width N` | Table width in characters (default: the terminal width). | `pprint --width 120 ps` |

### Modes

| Option | What it does |
| --- | --- |
| `-w`, `--watch` | Redraw the output every few seconds until Ctrl+C. |
| `-n SEC`, `--interval SEC` | Seconds between redraws (default 2, minimum 0.5). |
| `--once` | `stats`: print one snapshot instead of the live view. |
| `--full` | `inspect`: show every field as a tree instead of the summary. |
| `--raw` | Run the command untouched. |
| `--group` | `images`: one row per repository with total and unused size. |

### pprint clean

| Option | What it does |
| --- | --- |
| `--keep N` | Keep the newest N tags of each repository (default 3). |
| `--dry-run` | Only show the plan, delete nothing. |
| `-y`, `--yes` | Delete without asking. |

`--grep` limits `clean` and `doctor` to matching repositories or services.
`--full` makes `doctor` list every failed task.

### pprint errors

| Option | What it does |
| --- | --- |
| `--since TIME` | How far back to read logs: `30m` (default), `6h`, `2d`, `1w`, or a date. |
| `--grep REGEX` | Count only log lines matching this. |
| `--full` | Show every kind of message for each source, not just the top 10. |

Unlike other commands, `pprint errors` accepts its options anywhere:
`pprint errors api --since 2d` and `pprint --since 2d errors api` are the same.

### Output

| Option | What it does |
| --- | --- |
| `--no-color` | Turn colors off. |
| `--color` | Force colors, even into a pipe (useful with `less -R`). |
| `-V`, `--version` | Show the version. |
| `-h`, `--help` | Show all options with examples. |

If an unknown column name is given, pprint lists the available ones:

```
$ pprint --cols bogus ps
pprint: no column matches 'bogus'. Columns: container id, image, command, created, status, ports, names
```

---

## 6. Colors

| Column | Green | Yellow | Red | Grey |
| --- | --- | --- | --- | --- |
| STATUS (containers) | Up, healthy | health: starting, restarting, paused | unhealthy, exited with a non-zero code, dead | exited (0), created |
| STATUS (nodes) | Ready | | Down, Unknown | |
| REPLICAS | all running (`2/2`) | some running (`1/3`) | none running (`0/1`) | |
| CURRENT STATE (`service ps`) | Running | Pending, Preparing, Starting | Failed, Rejected | Shutdown, Complete |
| AVAILABILITY | Active | Pause, Drain | | |
| CPU % / MEM % | | 50% or more | 80% or more | |
| ERROR | | | any error | |
| REPOSITORY / IMAGE (`images`) | `●` used by a container | | | `○` not used |

Names are bold, headers are bold and borders are dimmed.

Colors turn off automatically when the output isn't a terminal (a pipe
or a file), or when the `NO_COLOR` environment variable is set. Use
`--color` to force them on.

---

## 7. Make plain `docker` use pprint

If you'd like `docker ps` itself to be formatted, without typing
`pprint`:

```sh
# bash
echo 'eval "$(pprint shell-init bash)"' >> ~/.bashrc
# zsh
echo 'eval "$(pprint shell-init zsh)"' >> ~/.zshrc
# fish
echo 'pprint shell-init fish | source' >> ~/.config/fish/config.fish
```

Then open a new terminal. This defines a small `docker` shell function:

* In your terminal, `docker ps` goes through pprint.
* In pipes and scripts (`docker ps | grep x`, `$(docker ps -q)`), docker's
  raw output is untouched, so nothing that parses docker output breaks.
* To skip pprint once, run `command docker ps`.

To see exactly what gets added, run `pprint shell-init bash`.

---

## 8. Default options

Put options you always want in the `PPRINT_OPTS` environment variable.
They're applied before the ones you type:

```sh
echo 'export PPRINT_OPTS="--short"' >> ~/.bashrc
```

---

## 9. Update

| Installed with | Update by |
| --- | --- |
| A. source archive | Copy the new archive over, then `rm -rf ~/pprint && tar -xzf pprint-source.tar.gz -C ~`. The `~/bin/pprint` launcher stays as it is. |
| B. git | `cd ~/pprint && git pull` |
| C. pip | `cd ~/pprint && git pull && python3 -m pip install --user --upgrade .` |
| D. single file | Build a new `dist/pprint` and copy it over the old one. |

Check with `pprint --version`.

---

## 10. Uninstall

1. **Remove the shell integration** if you added it (section 7). Delete the
   `pprint shell-init` line from `~/.bashrc`, `~/.zshrc` or
   `~/.config/fish/config.fish`, plus any `PPRINT_OPTS` line.

2. **Remove the program**, matching how you installed it:

   ```sh
   # A / B: source archive or git
   rm -f ~/bin/pprint
   rm -rf ~/pprint

   # A, installed for every user
   sudo rm -f /usr/local/bin/pprint
   sudo rm -rf /opt/pprint

   # C: pip
   python3 -m pip uninstall pprint-docker

   # D: single file
   rm -f ~/bin/pprint        # or wherever you copied it
   ```

3. Open a new terminal (or run `hash -r`) and check:

   ```sh
   type pprint               # should say "not found"
   ```

pprint doesn't change docker or any container, image or setting, and it
doesn't write any files of its own, so there's nothing else to clean up.

---

## 11. Troubleshooting

**`pprint: command not found`**
`~/bin` isn't on your PATH. Run `export PATH="$HOME/bin:$PATH"` and add
that line to `~/.bashrc`. Then run `hash -r`.

**`pprint --version` shows an old version, or the old behaviour**
An old alias or file is still in use. Run `type pprint`, then delete the
alias from `~/.bashrc` or the old file it points to, and open a new
terminal.

**`ImportError: cannot import name 'pprint' from 'pprint'`** (or other
Python errors mentioning pprint)
There's a file called `pprint.py` in your current folder or on
`PYTHONPATH`. It hides Python's built-in `pprint` module. Delete or
rename it.

**`No module named pprint_docker`**
The launcher can't find the source. Check that `~/pprint/src/pprint_docker`
exists. If you unpacked it somewhere else, fix the path in `~/bin/pprint`.

**`SyntaxError` when starting**
Python is older than 3.7. Check with `python3 --version`.

**`Cannot connect to the Docker daemon`**
That message comes from docker itself. Check that `docker ps` works
without pprint (permissions, `sudo`, or the `docker` group).

**No colors**
The output isn't going to a terminal, or `NO_COLOR` is set. Use `--color`
to force them.

**The table is too wide or wraps too much**
pprint uses the terminal width. Make the window wider, use `--cols` to
show fewer columns, use `--short` for image names, or set `--width`.

**The live view shows "… N more lines"**
The window isn't tall enough. Make it taller, or narrow the list with
`--grep` or `--cols`.

**A command hangs**
Docker commands that stream (`logs -f`, `events`, `stats`) are handled by
pprint and stop with Ctrl+C. A non-docker command that never finishes
will hang, because pprint waits for its output. Use `--raw` for those.

**`pprint errors` shows "! name: Error response from daemon: ... does not support reading"**
That container or service uses a logging driver docker can't read back
(for example `syslog` or `gelf` without dual logging). Its logs live in
that system instead, so pprint can't count them.

**`pprint errors` says "no stack, service or container called ..."**
Check the name with `pprint service ls`, `pprint stack ls` or
`pprint ps -a`. Stacks and services are only visible on a swarm manager.

**`--sort` or `--cols` passed to docker by mistake**
pprint's options must come before the command: `pprint --sort cpu stats`.

---

## 12. FAQ

**Does pprint change anything in docker?**
Only `pprint clean` deletes anything, and only image tags, after you
confirm. Everything else just runs the docker command you give it,
sometimes adding read-only display flags (`--no-trunc`, `--no-stream`),
and reformats the output.

**Can `pprint clean` delete an image a service needs?**
Not one that any container uses, running or stopped. But a service that
is scaled to 0, or a tag you plan to deploy later, has no container. If
you need such a tag, raise `--keep`, or check with `--dry-run` first.

**Is it safe in scripts?**
Scripts should call `docker` directly, or use `pprint --raw`. With the
shell integration from section 7, `docker` in pipes and scripts already
gets docker's raw output.

**Does it work with old docker versions?**
Yes. pprint asks docker for JSON where it can, which is exact even when
values contain spaces or cells are empty. If docker doesn't understand the
request, pprint quietly reads the normal text output instead.

**Can I still use `--format`?**
Yes. `pprint ps --format '{{.Names}}'` is passed straight through.
`--format 'table ...'` output is still formatted as a table.

**`pprint ps` runs docker, but I wanted Linux `ps`.**
pprint treats `ps` and `top` as docker commands. Use the full path for the
Linux tools: `pprint /bin/ps aux`.

**What is `dpp`?**
A short alias for `pprint`, installed by pip (method C).

**Does it need internet?**
No. It only needs Python 3.7+ and the docker CLI.

---

## 13. Development

### Project layout

```
pprint/
├── README.md
├── pyproject.toml          package metadata, `pprint` and `dpp` commands
├── Makefile                test / build / zipapp shortcuts
├── src/pprint_docker/
│   ├── __main__.py         `python3 -m pprint_docker` starts here
│   ├── cli.py              options and dispatch to the right feature
│   ├── docker.py           which docker command is it; flags to add
│   ├── table.py            Table model; parsing column-aligned output
│   ├── formats.py          reading list commands as JSON (with text fallback)
│   ├── layout.py           column widths, wrapping, drawing the box
│   ├── transform.py        short IDs/ages/images, --cols, --sort, --grep
│   ├── styles.py           which cell gets which color
│   ├── ansi.py             color codes; measuring text without them
│   ├── runner.py           running commands (captured or attached)
│   ├── options.py          settings shared by all features
│   ├── units.py            sizes and times: parsing and printing
│   └── features/
│       ├── tables.py       list commands as tables
│       ├── live.py         full-screen redraw (stats, --watch, dash --watch)
│       ├── logs.py         colored logs and --grep
│       ├── inspect.py      inspect summaries and JSON tree
│       ├── dashboard.py    pprint dash
│       ├── images.py       in-use marks, image data, images --group
│       ├── clean.py        pprint clean
│       ├── doctor.py       pprint doctor
│       ├── errors.py       pprint errors
│       └── shell.py        pprint shell-init
└── tests/
    ├── fixtures/           real docker output recorded for the tests
    ├── fake_docker.py      stand-in docker used by the end-to-end tests
    └── test_*.py
```

### How a command flows

1. `cli.py` reads pprint's options and adds `docker` in front if you left
   it out.
2. `docker.py` classifies the command as table, stats, logs, inspect or
   passthrough.
3. Passthrough commands run attached to your terminal, untouched.
4. Table commands run with their output captured. For `ps`, `images`,
   `service ls`/`ps`, `stack ps`, `node ls`/`ps` and `stats`, `formats.py`
   asks docker for one JSON object per row (a `--format` template naming
   each field) and builds the table with docker's own headers. Every other
   table command, and a docker too old for the template, goes through
   `table.py`, which finds the column boundaries from the header
   positions. Then `transform.py` shortens, filters and sorts, and
   `layout.py` draws the table with colors from `styles.py`.

### Run from source without installing

```sh
cd ~/pprint
PYTHONPATH=src python3 -m pprint_docker ps
```

### Tests

```sh
python3 -m pip install pytest      # once
make test                          # or: PYTHONPATH=src python3 -m pytest -q
```

The tests use recorded docker output and a fake `docker`, so they run
without a docker daemon.

### Build

```sh
make zipapp        # dist/pprint, one executable file
make build         # wheel + sdist in dist/ (needs: pip install build)
make clean         # remove build output
```

### Adding a new table command

Add it to `TABLE_COMMANDS` in `src/pprint_docker/docker.py`. If docker
supports `--no-trunc` for it, add it to `NO_TRUNC` as well. To read it as
JSON, add its columns (header and `--format` field) to `LAYOUTS` in
`formats.py` and a JSON fixture to `tests/fixtures`. To color a new
column, add a rule in `styles.py`. Add a test in `tests/test_docker.py`.
