# Troubleshooting account setup

[Documentation index](README.md)

## What an email-code request error means

Account setup contacts `9.moto.5gencare.com` over certificate-verified TLS on
TCP port 3388. There is no hardcoded country, country code, language or region
parameter in the login request. The vendor can return another server within
`*.moto.5gencare.com`; the integration follows that route when submitting the
code. Other routing domains are currently rejected. Other regions have not yet
been validated.

A code-request error can mean a vendor rejection or an unexpected response,
including an unsupported routing host. It does not by itself prove rate limiting
or an incorrect email address. This happens before camera discovery, so it also
does not establish whether a particular camera model is compatible.

## Collect logs when the first setup cannot finish

Update the integration in HACS and restart Home Assistant to load the new files.
Then enable logging **before** submitting the email form. If setup has never
completed, the integration's debug button or diagnostics download may not be
available. Use this method instead; it does not require another restart:

1. Open **Developer tools > Actions** and switch to YAML mode.
2. Run:

   ```yaml
   action: logger.set_level
   data:
     custom_components.motorola_nursery: debug
   ```

3. Open **Settings > Devices & services > Add integration > Motorola Nursery**
   and reproduce the failure once. Note the approximate time. Do not keep
   requesting codes repeatedly. If a code arrives, do not share it.
4. Open **Settings > System > Logs**, select **Home Assistant Core** if a source
   selector is present, and use **Download full logs**. Filter the downloaded
   file to lines containing `custom_components.motorola_nursery` around the
   attempt. The new account messages start with `Account`.
5. Restore the log level with the same action, changing `debug` to `warning`.
   If you previously configured another level, restore that level instead.
6. Review the selected lines and attach them as a `.txt` file to the issue.
   Do not post the complete HA log: other integrations can log private data.

If `logger.set_level` is unavailable, add the following to the existing
`logger:` configuration (do not create a duplicate section), then restart HA:

```yaml
logger:
  default: warning
  logs:
    custom_components.motorola_nursery: debug
```

Reproduce once, download and review the logs as above, then remove this debug
setting and restart HA when convenient.

## Existing installations

For an integration that already has an entry, use **Settings > Devices &
services > Motorola Nursery > three-dot menu > Enable debug logging**. Reproduce
the problem, then choose **Disable debug logging** to download the log.
**Download diagnostics**, when available, also includes integration and HA
versions and connection/capability counters. Diagnostics are supplementary:
they do not contain the failed first-setup exchange.

See Home Assistant's [debug logging and diagnostics guide](https://www.home-assistant.io/docs/configuration/troubleshooting/#debug-logs-and-diagnostics).

## What to include in an issue

- Integration and Home Assistant versions.
- Camera model and firmware, if known.
- Your country/region and the exact mobile app name and version. Region is
  supplied by you; the integration does not infer or collect it.
- Whether a **fresh sign-in code** can be requested and received using the
  official app. An existing signed-in session does not test code delivery.
  Avoid signing out of your only working app session just for this test.
- Approximate attempt time and the reviewed integration log excerpt.

Debug logs report connection stage, DNS/TLS/timeout categories, operation names,
response field counts, first-field category, short negative numeric vendor
statuses, elapsed time, and whether the vendor redirects login. Numeric status
meanings are not assumed. They omit emails, codes, client/account/device IDs,
tokens, credentials, camera names/addresses, raw responses and routing hostnames.
No logs or diagnostics are sent automatically to the maintainer.

For example, `operation=v3_otp fields=1 first=negative_status status=-10`
followed by `reason=server_rejected` distinguishes a vendor refusal from
`reason=unexpected_response` or `reason=unsupported_routing_host`. It does not
explain an undocumented vendor status on its own. These logs narrow the next
investigation; additional evidence may still be necessary.
