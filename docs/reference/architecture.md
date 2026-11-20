# Architecture

[Documentation index](../README.md)

## Runtime ownership

`__init__.py` owns each entry's runtime and cleanup. Local video, account access
and camera data are independent paths. Initial telemetry and playlist requests
run in the background so delayed responses do not block local camera startup.

| Path | Modules | Responsibility |
| --- | --- | --- |
| Video | `protocol.py`, `bridge.py`, `transcoder.py`, `camera.py` | Camera TCP tunnel, loopback RTSP bridge and on-demand FFmpeg relay. |
| Account | `cloud.py`, `auth.py`, `config_flow.py` | Email-code login, session storage and credential renewal. |
| Camera data | `telemetry.py`, `coordinator.py`, `events.py`, entity platforms | Allowlisted settings, capability discovery, polling, playlists and detections. |
| Incoming LAN | `f3.py`, `local.py` | Shared authenticated listener and camera-initiated readings, controls and events. |

## Playback

The camera's TCP port 77 tunnels its internal RTSP service. Private loopback
listeners feed FFmpeg and Home Assistant Stream. H.264 video is copied and PCMA
audio becomes AAC. Still images use the same native Home Assistant stream
worker as HLS playback, sharing decoded frames and avoiding an additional snapshot
ingest pipeline. Each still request waits for a new keyframe so a disconnected
stream does not immediately return its cached image. Snapshot requests renew the
native stream's idle timer, allowing repeated captures to keep the worker active
and Home Assistant to release it after requests stop. Viewers share managed
resources; telemetry outages do not interrupt local video. The relay terminates
its FFmpeg process when the native stream consumer disconnects or media output
stalls for 30 seconds, allowing HA to retry without retaining an idle ingestion.
Integration startup uses saved camera credentials. The camera must have
initialized its local service; the integration does not emulate
every external camera initialization service. See the physical
[startup limits](../guides/compatibility.md#network-and-account-limits).

## Account and camera data

Default camera data uses cloud transport. Readings share a 60-second poll and
do not rotate account sessions; detections use a persistent connection. Commands
are allowlisted and validated against camera-advertised access and bounds.
Settings are read back before state updates. Playlist loading is separate from
readings and does not play audio during discovery.

Account-connected entries can renew credentials after a failed local connection,
with a cooldown. Rotated cloud tokens are saved before further requests. Rejected
sessions request HA reauthentication; another email code requires submitting the
email form. Manual-only entries retain local video.

## Incoming LAN transport

The camera connects to HA TCP 2278 through an explicit router redirect. One shared
listener authenticates and routes registered camera connections. The local
adapter reuses allowlisted command and capability handling without creating a
cloud session. A disconnect invalidates live availability and cached capabilities;
entities retain identities while the camera reconnects. Playlist failure after
a fully consumed response leaves readings/events connected; framing errors close
the peer to prevent request/response desynchronization.

Local mode disables automatic cloud renewal and has no cloud fallback. See
[local readings](../guides/local-readings.md) for routing requirements.

## Cleanup

Unload cancels entry-owned tasks, listeners, clients, peer connections and FFmpeg
processes. Pending telemetry and playlist work must stop with the entry. Keep
blocking work off the event loop and bound buffering and retry work. Automated
checks use synthetic peers; see [testing](../development/testing.md).

See the [implemented protocol](protocol.md) for current transport formats and limits.

## Beta local provisioning

`config_flow_local.py` owns the native QR and a ten-minute enrollment window.
`bootstrap.py` generates local credentials and serves source-restricted F3 `dreg`
enrollment on3378, exact clock requests on4400 and selector HTTP-DNS on40280. The provisional incoming
control registration allows verification of device initialization and video
before persistence; after a video failure, explicit user confirmation can instead
preserve an authenticated pairing for further media diagnosis. Final entry setup
starts its normal local control transport
and registers its clock and HTTP-DNS peers; unload releases all three services. No cloud session is
created and local playback never invokes account renewal.

LAN DNS directs the camera's suffixed selector to HA. Locally provisioned control
connects directly to HA without a gateway DNAT/SNAT rule. Network routing remains
external to the integration; local provisioning does not itself eliminate
firmware public-IP connectivity probes or SDK HTTP-DNS routing. The bounded
HTTP-DNS listener answers only the HA selectors registered for the requesting
camera, with no upstream resolution or proxying. Requests to public resolver
addresses require external forwarding that preserves the camera source address. See the [pairing guide](../guides/local-pairing.md).

Wi-Fi reconfiguration borrows the existing authenticated control registration,
adds temporary clock and HTTP-DNS peers for the candidate address, and reuses saved
camera credentials during enrollment. It requires a ready peer from that address;
a connection from the old address cannot satisfy migration validation. Only the
host/server fields are updated after confirmation. Cleanup unregisters the flow's
provisional resources without retiring the entry's existing registration.

For Wi-Fi moves to a different address, the flow may verify a new incoming session
using the saved credentials instead of requiring a second enrollment reply. It
must differ from the session present when QR setup started and must match the
candidate address. This path also requires successful local video authentication;
the save-without-video option is unavailable without enrollment acknowledgement.
Fresh provisioning and same-address Wi-Fi changes still require enrollment.
