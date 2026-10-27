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

## Guides

- [Development and maintenance](docs/development.md): architecture, local test
  environments, CI, releases and live validation.
- [Protocol reference](docs/protocol.md): transports, authentication, verified
  values and controls, and compatibility limits.
- [Documentation index](docs/README.md): all maintained project guides.

## Pull requests

The `main` branch requires pull requests and blocks force pushes and deletion.
Merge requires an up-to-date branch, resolved review
conversations, one approving review, and passing HACS, Hassfest, minimum/current
HA tests, both CodeQL analyses and CodeRabbit checks. Use squash merge with a clear
PR title and description; these become the commit title and body.

- Keep changes focused and explain user-visible behavior.
- Add or update tests for every behavior change.
- Update translations, documentation, and the changelog when applicable.
- Preserve local video when cloud services are unavailable.
- Keep diagnostics and exceptions free of sensitive data.
- Do not add arbitrary command execution, firmware, reset, storage-formatting,
  debug-shell, or credential-export features.

By participating, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
