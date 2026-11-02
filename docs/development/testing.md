# Development and testing

[Documentation index](../README.md)

Run commands from the repository root. See [architecture](../reference/architecture.md)
for module responsibilities.

Use Python 3.14 and a virtual environment:

```sh
python3.14 -m venv .venv
.venv/bin/pip install -r requirements-test.txt
```

The pinned HA test plugin selects compatible Home Assistant, pytest,
pytest-asyncio and coverage versions. Update that plugin rather than adding
independent pins for those packages. Shared tools live in
`requirements-test-tools.txt`.

CI tests the minimum supported HA and the version selected by
`requirements-test.txt`. The minimum plugin pin lives in
`requirements-test-minimum.txt`; update it only when intentionally raising the
documented minimum HA version. Both CI environments use complete, hash-locked
Linux x86_64 / Python 3.14 dependencies. See
[lock maintenance](#dependency-lock-maintenance) before updating pins.
To reproduce either CI environment, create a separate virtual environment:

```sh
python -m pip install --require-hashes --only-binary=:all: -r requirements-test-build.lock
python -m pip install --require-hashes --only-binary=:all: --no-binary=mock-open,pyric --no-build-isolation -r requirements-test-current.lock
python -m pip check
```

Replace `current` with `minimum` for the compatibility suite. The two explicitly
allowed source packages have no published wheels; their archives and build tools
are hash-locked, and build isolation is disabled to prevent unpinned build-time
downloads. Do not widen that exception without reviewing the dependency.

For code changes, run the complete local validation before opening a pull request:

```sh
.venv/bin/ruff check custom_components tests scripts
.venv/bin/ruff format --check custom_components tests scripts
.venv/bin/bandit -q -r custom_components/motorola_nursery scripts
.venv/bin/coverage run -m pytest -q
.venv/bin/coverage report --fail-under=80
```

Tests must not contact Motorola services, send email, control a real camera, or
depend on personal credentials. Use synthetic protocol fixtures and reserved
documentation addresses.

Cover failure and cancellation paths as well as successful responses. In
particular, check that cloud failures preserve local video, delayed discovery
creates no duplicate entities, viewer disconnects do not trigger credential
recovery, and unload closes clients, background tasks and FFmpeg processes.

## Dependency lock maintenance

Direct pins live in `requirements-test*.txt`; CI installs the complete hashed
`requirements-test-{current,minimum,build}.lock` files. Update inputs and locks
together. Regenerate with:

```sh
python scripts/lock_test_dependencies.py
```

The generator targets Linux x86-64 and the Python patch level defined in its
source. Pass `current`, `minimum` or `build` for selected locks. Use `--upgrade`
only for an intentional full refresh or `--upgrade-package NAME` for a targeted
update. Review transitive changes and run both HA test environments.

Locks record a digest of recursively expanded inputs, including extras and
markers. The generator checks that inputs did not change during compilation and
publishes outputs atomically. Do not edit the digest manually. Metadata tests
reject input/lock drift. Only `mock-open` and `pyric` are source-build exceptions;
their archives and build tools stay hash-locked with build isolation disabled.
