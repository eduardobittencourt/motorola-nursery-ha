# Contributor guidance

Use Portuguese when discussing changes with the owner. Keep public code,
comments and maintained project documentation in English.

Review concrete correctness, security and regression risks. Explain the trigger
and impact of each finding; avoid repeating formatter output or speculative
refactors. Preserve config-entry migrations, entity unique IDs and supported HA
versions. Keep blocking work off Home Assistant's event loop; bound queues and
clean up tasks, sockets, threads and child processes on failure, cancellation
and unload. Never log credentials or publish private device data.

Fix root causes without weakening tests, suppressing findings indiscriminately,
reducing coverage requirements or bypassing release/merge checks. Use synthetic
peers for protocol tests; hardware operations need explicit scope. Follow the
repository's development guide and run its relevant checks before proposing a
fix. Read docs/sonarqube.md for the review and coverage workflow.

The product is custom_components/motorola_nursery. Preserve local video when
cloud telemetry fails. Commands require camera-advertised writable capabilities,
valid bounds and the existing allowlist. Keep incoming LAN and cloud transport
semantics distinct; do not add cloud fallback to LAN mode. Never infer PTZ from
model name alone. Development: docs/development.md.
