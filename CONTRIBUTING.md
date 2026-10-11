# Contributing

Run from a checkout:

```sh
PYTHONPATH=src python3 -m dkview ps
```

## Tests

```sh
pip install pytest
make test
```

These use recorded output and a fake `docker`, no daemon needed.

`make test-real` runs against a real daemon. It creates a swarm and
`rt_*` services and removes them afterwards, so use a throwaway machine.
`DKVIEW_ENGINE=podman make test-real` for Podman.

## New table commands

Add the command to `TABLE_COMMANDS` in `src/dkview/docker.py` (and
`NO_TRUNC` if it takes `--no-trunc`). For JSON parsing, add its columns to
`LAYOUTS` in `formats.py` with a fixture in `tests/fixtures`.
