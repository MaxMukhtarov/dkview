PYTHON ?= python3

.PHONY: test test-real build check zipapp install clean

test:
	PYTHONPATH=src $(PYTHON) -m pytest -q

# Against the real docker daemon: creates a swarm (if needed), a stack, services
# and containers named rt_*, and removes them afterwards. Needs busybox:latest.
test-real:
	REAL_DOCKER=1 PYTHONPATH=src $(PYTHON) -m pytest -v tests/real

# Wheel and sdist in dist/, for `pip install`.
build:
	$(PYTHON) -m build

# Build, then check that PyPI will accept the metadata and render the README.
check: build
	$(PYTHON) -m twine check --strict dist/dkview-[0-9]*

# One executable file, dist/dkview, that needs nothing but python3.
# Copy it to a server and run it; no pip required.
zipapp:
	rm -rf build/zipapp && mkdir -p build/zipapp dist
	cp -r src/dkview build/zipapp/
	find build/zipapp -name __pycache__ -prune -exec rm -rf {} +
	$(PYTHON) -m zipapp build/zipapp -m "dkview.cli:main" \
		-p "/usr/bin/env python3" -c -o dist/dkview
	chmod +x dist/dkview
	@echo "built dist/dkview"

install:
	$(PYTHON) -m pip install --user .

clean:
	rm -rf build dist src/*.egg-info .pytest_cache
	find . -name __pycache__ -prune -exec rm -rf {} +
