# Contributing

Thanks for helping improve Motorola Nursery for Home Assistant.

## Before you start

- Search existing issues before opening a new one.
- Use a feature request for protocol or device support discussions.
- Never post account identifiers, email codes, camera addresses, stream URLs,
  tokens, credentials, packet captures, APKs, firmware, or proprietary binaries.
- Report vulnerabilities privately as described in [SECURITY.md](SECURITY.md).

This project is an independent interoperability implementation. Contributions
must be original and must not copy decompiled vendor source or proprietary
libraries into the repository.

## Development setup

Use Python 3.14 and a virtual environment:

```sh
python3.14 -m venv .venv
.venv/bin/pip install -r requirements-test.txt
```

Run the complete local validation before opening a pull request:

```sh
.venv/bin/ruff check custom_components tests
.venv/bin/ruff format --check custom_components tests
.venv/bin/bandit -q -r custom_components/motorola_nursery
.venv/bin/coverage run --source=custom_components/motorola_nursery -m pytest -q
.venv/bin/coverage report --fail-under=80
```

Tests must not contact Motorola services, send email, control a real camera, or
depend on personal credentials. Use synthetic protocol fixtures and reserved
documentation addresses.

## Pull requests

- Keep changes focused and explain user-visible behavior.
- Add or update tests for every behavior change.
- Update translations, documentation, and the changelog when applicable.
- Preserve local video when cloud services are unavailable.
- Keep diagnostics and exceptions free of sensitive data.
- Do not add arbitrary command execution, firmware, reset, storage-formatting,
  debug-shell, or credential-export features.

By participating, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
