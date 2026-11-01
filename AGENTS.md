# Contributor guidance

Start with [CONTRIBUTING.md](CONTRIBUTING.md) and
[docs/development.md](docs/development.md) for development commands.
Use English for public code comments, documentation and review feedback.

- The product is the Home Assistant integration in
  `custom_components/motorola_nursery`. Preserve local video when cloud
  telemetry is unavailable.
- Commands require camera-advertised writable capabilities, valid bounds and
  the existing allowlist. Do not infer PTZ support from a model name alone.
- Keep incoming LAN and cloud transport semantics distinct. LAN mode must not
  silently fall back to cloud connections.
- Preserve config-entry migrations, entity unique IDs and supported Home
  Assistant versions. Add regression tests when changing persisted data or
  observable behavior.
- Keep blocking work off Home Assistant's event loop. Bound queues and release
  tasks, sockets, threads and child processes on failure, cancellation and unload.
- Keep credentials and private device data out of logs, diagnostics, fixtures
  and contributions. Use synthetic peers for automated protocol tests and
  document physical-device verification separately.
- Run Ruff, Bandit and relevant pytest tests from the development guide. Fix
  underlying failures without weakening assertions or bypassing CI requirements.

See [SonarQube Cloud and coverage](docs/sonarqube.md) for CI coverage reporting
and review configuration.
