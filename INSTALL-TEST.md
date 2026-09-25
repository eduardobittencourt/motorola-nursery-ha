# Home Assistant validation plan — 0.2.0-dev.2

The package contains only custom_components/motorola_nursery. No account
configuration, capture or research tooling is included.

## Before installing

1. Back up the current custom_components/motorola_nursery directory.
2. Back up the existing Motorola config-entry data securely, and record the
   entry/entity identifiers. Do not publish the config-entry backup.
3. Replace the integration files, run HA configuration validation, then restart
   Home Assistant. This interrupts other integrations briefly.

## Live acceptance

1. Confirm the existing camera entity still provides a snapshot and playback.
2. Open the integration entry menu, choose Reconfigure, then account login.
3. Enter the email and the received code in HA, and confirm the camera IP.
4. Confirm the same entity ID remains, snapshot works and HLS has audio.
5. Restart HA and check playback using the saved credentials.
6. Check sanitized diagnostics and logs. Do not force token expiry or alter the
   working account just to exercise an artificial failure.

## Rollback

Restore the previous integration directory and restart HA. The account-enabled
entry retains the old local credential fields, so the previous integration can
read it. Restore saved config-entry data only if necessary, with HA stopped;
restoring an old cloud token does not undo vendor-side token rotation and may
require a fresh email login when upgrading again.
