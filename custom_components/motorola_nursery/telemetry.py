"""Read-only, certificate-verified Motorola camera telemetry.

This service is separate from the local video tunnel and account-login service.
Only app authentication, capability discovery, getters and keepalives are sent.
"""

from __future__ import annotations

import asyncio
import re
import ssl
from contextlib import suppress
from dataclasses import dataclass, field

from .cloud import atom, vendor_host
from .protocol import Credentials

CONTROL_PORT = 2288
MAX_LINE = 65536
TIMEOUT = 15

# Deliberately exclude identity, network names, playlists and all write commands.
READABLE_FIELDS = frozenset(
    {
        "temperature_reading",
        "wifi_signal",
        "hardware_version",
        "firmware_version",
        "videoKbps",
        "video_brightness",
        "speaker_volume",
        "motion",
        "sound",
        "night_vision",
        "ceiling_mount",
        "temperature_low",
        "temperature_high",
        "lowtemp_switch",
        "hightemp_switch",
        "video[0].motion_zone",
        *(f"video[0].motion.zone[{index}].enable" for index in range(4)),
    }
)


class TelemetryError(Exception):
    """A safe error without wire data or credentials."""


@dataclass(frozen=True, slots=True)
class Capability:
    """Advertised bounds, retained only for explicitly supported getters."""

    kind: str
    minimum: int
    maximum: int


@dataclass(frozen=True, slots=True)
class TelemetryData:
    """One complete read, containing no account or network identifiers."""

    capabilities: dict[str, Capability] = field(default_factory=dict)
    values: dict[str, int | str | None] = field(default_factory=dict)


def parse_capabilities(parts: list[str]) -> dict[str, Capability]:
    """Validate count and five-field rows before selecting known capabilities."""
    try:
        count = int(parts[1])
        if parts[0] != "caplist" or not 0 <= count <= 256:
            raise ValueError
        if len(parts) != 2 + count * 5:
            raise ValueError
        result = {}
        seen = set()
        for index in range(2, len(parts), 5):
            key, access, kind, low, high = parts[index : index + 5]
            if key in seen:
                raise ValueError
            seen.add(key)
            if key not in READABLE_FIELDS:
                continue
            minimum, maximum = int(low), int(high)
            expected = "str" if key.endswith("_version") else "int"
            if access not in {"r", "w"} or kind != expected or minimum > maximum:
                raise ValueError
            result[key] = Capability(kind, minimum, maximum)
        return result
    except (ValueError, IndexError):
        raise TelemetryError("Invalid capability response") from None


def parse_values(
    parts: list[str], capabilities: dict[str, Capability]
) -> dict[str, int | str | None]:
    """Reject incomplete responses; isolate invalid individual sensor values."""
    try:
        count = int(parts[1])
        if parts[0] != "get" or count != len(capabilities):
            raise ValueError
        if len(parts) != 2 + count * 2:
            raise ValueError
        raw = dict(zip(parts[2::2], parts[3::2], strict=True))
        if len(raw) != count or raw.keys() != capabilities.keys():
            raise ValueError
    except (ValueError, IndexError):
        raise TelemetryError("Invalid sensor response") from None

    result: dict[str, int | str | None] = {}
    for key, value in raw.items():
        cap = capabilities[key]
        if cap.kind == "str":
            result[key] = (
                value if re.fullmatch(r"[A-Za-z0-9._-]{1,64}", value) else None
            )
            continue
        try:
            number = int(value)
            result[key] = number if cap.minimum <= number <= cap.maximum else None
        except ValueError:
            result[key] = None
    return result


class TelemetryClient:
    """Use saved per-camera credentials without rotating the account session."""

    def __init__(self, host: str, context: ssl.SSLContext) -> None:
        self.host = vendor_host(host)
        self._context = context
        self._capabilities: dict[str, Capability] | None = None
        self._lock = asyncio.Lock()

    async def async_read(self, credentials: Credentials) -> TelemetryData:
        """Open one bounded TLS session and read only allowlisted properties."""
        # Validate before opening a connection, including legacy imported data.
        owner = atom(str(credentials.sid_user_id))
        token = atom(credentials.magic_token.decode("ascii"))
        async with self._lock:
            writer: asyncio.StreamWriter | None = None
            try:
                async with asyncio.timeout(TIMEOUT):
                    reader, writer = await asyncio.open_connection(
                        self.host,
                        CONTROL_PORT,
                        ssl=self._context,
                        server_hostname=self.host,
                        limit=MAX_LINE,
                    )

                    async def exchange(message: str, expected: str) -> list[str]:
                        writer.write(message.encode("ascii") + b"\n")
                        await writer.drain()
                        for _ in range(32):
                            line = await reader.readline()
                            if (
                                not line
                                or len(line) > MAX_LINE
                                or not line.endswith(b"\n")
                            ):
                                raise TelemetryError("Incomplete control response")
                            parts = line.decode("ascii").split()
                            if parts == ["ping"]:
                                writer.write(b"pong\n")
                                await writer.drain()
                            elif parts == ["pong"]:
                                writer.write(b"pang\n")
                                await writer.drain()
                            elif parts and parts[0] == expected:
                                return parts
                        raise TelemetryError("Too many unrelated control messages")

                    if await exchange(f"app {owner} {token}", "app") != [
                        "app",
                        "1",
                        "OK",
                    ]:
                        raise TelemetryError(
                            "Camera telemetry authentication unavailable"
                        )
                    caps = self._capabilities
                    if caps is None:
                        caps = parse_capabilities(await exchange("caplist", "caplist"))
                    if not caps:
                        self._capabilities = caps
                        return TelemetryData()
                    keys = sorted(caps)
                    parts = await exchange(f"get {len(keys)} {' '.join(keys)}", "get")
                    values = parse_values(parts, caps)
                    self._capabilities = caps
                    return TelemetryData(dict(caps), values)
            except TelemetryError:
                self._capabilities = None
                raise
            except (OSError, EOFError, ValueError, TimeoutError):
                self._capabilities = None
                raise TelemetryError("Unable to read camera telemetry") from None
            finally:
                if writer is not None:
                    writer.close()
                    with suppress(OSError, TimeoutError):
                        async with asyncio.timeout(2):
                            await writer.wait_closed()
