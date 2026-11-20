"""Bounded local bootstrap and explicitly armed camera enrollment listeners."""

from __future__ import annotations

import asyncio
import hmac
import ipaddress
import json
import logging
import secrets
import string
import time
from contextlib import suppress
from datetime import UTC, datetime
from urllib.parse import parse_qsl, quote, urlsplit

from nacl.exceptions import CryptoError

from .auth import credentials_from_data, device_data
from .cloud import Device
from .f3 import F3Connection
from .protocol import Credentials

CLOCK_PORT = 4400
HTTP_DNS_PORT = 40280
ENROLLMENT_PORT = 3378
PAIRING_SECONDS = 600
MODEL = "VM65CONNECT"
_LOGGER = logging.getLogger(__name__)


def lan_address(value: str) -> str:
    """Require an explicit unicast RFC1918 address, never resolve hostnames."""
    address = ipaddress.IPv4Address(value.strip())
    if not any(
        address in ipaddress.ip_network(network)
        for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
    ):
        raise ValueError("A private LAN address is required")
    return str(address)


def clock_field() -> str:
    """Use current UTC, with the camera's BusyBox date syntax."""
    now = datetime.now(UTC)
    if not 2020 <= now.year <= 2100:
        raise ValueError("System clock unavailable")
    return now.strftime("%m%d%H%M%Y.%S")


class BoundedListener:
    """Limit connections, framing, request time and shutdown work."""

    def __init__(self, port: int):
        self.port = port
        self.server = None
        self.tasks: set[asyncio.Task] = set()
        self._window = 0
        self._attempts = 0

    def allows(self, peer: str) -> bool:
        raise NotImplementedError

    async def start(self) -> None:
        if self.server is not None:
            return
        self.server = await asyncio.start_server(
            self._accept,
            "0.0.0.0",
            self.port,
            limit=4097,  # nosec B104
        )
        self.port = self.server.sockets[0].getsockname()[1]

    def _accept(self, reader, writer) -> None:
        window = int(time.monotonic())
        if window != self._window:
            self._window, self._attempts = window, 0
        self._attempts += 1
        if (
            not self.allows(writer.get_extra_info("peername")[0])
            or len(self.tasks) >= 4
            or self._attempts > 16
        ):
            writer.close()
            return
        task = asyncio.create_task(self._run(reader, writer))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def _run(self, reader, writer) -> None:
        try:
            async with asyncio.timeout(12):
                await self.handle(reader, writer)
        except (
            OSError,
            EOFError,
            ValueError,
            CryptoError,
            asyncio.LimitOverrunError,
        ) as error:
            _LOGGER.debug(
                "Local bootstrap request closed: category=%s", type(error).__name__
            )
        finally:
            writer.close()
            with suppress(OSError, TimeoutError):
                await asyncio.wait_for(writer.wait_closed(), 1)

    async def handle(self, reader, writer) -> None:
        raise NotImplementedError

    async def stop(self) -> None:
        server, self.server = self.server, None
        if server:
            server.close()
        tasks = tuple(self.tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if server:
            try:
                async with asyncio.timeout(3):
                    await server.wait_closed()
            except TimeoutError:
                server.abort_clients()


class LocalClockServer(BoundedListener):
    """One clock endpoint shared only by explicitly registered camera peers."""

    def __init__(self, port: int = CLOCK_PORT):
        super().__init__(port)
        self.peers: dict[str, str] = {}
        self.lock = asyncio.Lock()

    def allows(self, peer: str) -> bool:
        return peer in self.peers.values()

    async def register(self, key: str, peer: str) -> None:
        async with self.lock:
            await self.start()
            self.peers[key] = peer

    async def unregister(self, key: str) -> None:
        async with self.lock:
            self.peers.pop(key, None)
            if not self.peers:
                await self.stop()

    async def handle(self, reader, writer) -> None:
        async with asyncio.timeout(3):
            if await reader.readuntil(b"\n") != b"config\n":
                raise ValueError("Unsupported clock request")
            writer.write(f"config {clock_field()} false\n".encode())
            await writer.drain()


class LocalHttpDnsServer(BoundedListener):
    """Resolve only each registered camera's configured HA selector, locally."""

    def __init__(self, port: int = HTTP_DNS_PORT):
        super().__init__(port)
        self.peers: dict[str, tuple[str, str]] = {}
        self.lock = asyncio.Lock()

    def allows(self, peer: str) -> bool:
        return any(camera == peer for camera, _ in self.peers.values())

    async def register(self, key: str, peer: str, server: str) -> None:
        server = lan_address(server)
        async with self.lock:
            await self.start()
            self.peers[key] = (peer, server)

    async def unregister(self, key: str) -> None:
        async with self.lock:
            self.peers.pop(key, None)
            if not self.peers:
                await self.stop()

    async def handle(self, reader, writer) -> None:
        async with asyncio.timeout(3):
            request = await reader.readuntil(b"\r\n\r\n")
            if len(request) > 4096:
                raise ValueError("HTTP-DNS headers too large")
            try:
                first, *headers = request.decode("ascii").split("\r\n")
            except UnicodeError:
                raise ValueError("Invalid HTTP-DNS encoding") from None
            parts = first.split(" ")
            if (
                len(parts) != 3
                or parts[0] != "GET"
                or parts[2]
                not in (
                    "HTTP/1.0",
                    "HTTP/1.1",
                )
            ):
                raise ValueError("Unsupported HTTP-DNS request")
            for header in filter(None, headers):
                name, separator, value = header.partition(":")
                if (
                    not separator
                    or not name
                    or any(
                        c not in string.ascii_letters + string.digits + "-"
                        for c in name
                    )
                    or name.lower() == "transfer-encoding"
                    or (name.lower() == "content-length" and value.strip() != "0")
                ):
                    raise ValueError("Unsupported HTTP-DNS header")
            target = urlsplit(parts[1])
            if (
                target.scheme
                or target.netloc
                or target.fragment
                or target.path != "/199714/resolve"
            ):
                raise ValueError("Unsupported HTTP-DNS target")
            fields = parse_qsl(target.query, strict_parsing=True, max_num_fields=2)
            query = dict(fields)
            if (
                len(fields) != 2
                or set(query) != {"host", "udid"}
                or not 1 <= len(query["udid"]) <= 16
                or not query["udid"].isascii()
                or not query["udid"].isdecimal()
            ):
                raise ValueError("Unsupported HTTP-DNS query")
            peer = writer.get_extra_info("peername")[0]
            address = next(
                (
                    server
                    for camera, server in self.peers.values()
                    if camera == peer
                    and query["host"]
                    in (f"{server}.5gencare.com", f"{server}.5gencare.com.lan")
                ),
                None,
            )
            if address is None:
                raise ValueError("Unregistered HTTP-DNS selector")
            body = json.dumps(
                {"dns": [{"host": query["host"], "ips": [address]}]},
                separators=(",", ":"),
            ).encode("ascii")
            writer.write(
                b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                b"Connection: close\r\nCache-Control: no-store\r\nContent-Length: "
                + str(len(body)).encode("ascii")
                + b"\r\n\r\n"
                + body
            )
            await writer.drain()


class LocalEnrollment(BoundedListener):
    """One short-lived, source-bound QR enrollment, with fresh local credentials."""

    def __init__(
        self,
        peer: str,
        port: int = ENROLLMENT_PORT,
        *,
        device: Device | None = None,
        credentials: Credentials | None = None,
    ):
        super().__init__(port)
        self.peer = peer
        self.account = str(100_000_000 + secrets.randbelow(900_000_000))
        self.deadline = time.monotonic() + PAIRING_SECONDS
        alphabet = string.ascii_letters + string.digits
        random_device = "".join(secrets.choice(alphabet) for _ in range(20))
        random_magic = "".join(secrets.choice(alphabet) for _ in range(27))
        self.device = Device(
            str(100_000 + secrets.randbelow(900_000)),
            "pending",
            MODEL,
            "Motorola%20camera",
            random_magic,
            random_device,
            "-1",
        )
        if device is not None:
            if device.model != MODEL or credentials is None:
                raise ValueError("Unsupported saved pairing")
            credentials.validate()
            if (
                credentials.sid_user_id != int(device.owner_id)
                or credentials.sid_device != device.sid_device.encode()
                or credentials.magic_token != device.magic_token.encode()
            ):
                raise ValueError("Saved pairing credentials do not match")
            self.device = device
        elif credentials is not None:
            raise ValueError("Saved device required")
        self.identifier: str | None = None
        self.registered = asyncio.Event()
        self.attempts = 0
        self.credentials = credentials or credentials_from_data(
            device_data(self.device)
        )
        self.credentials.validate()

    def allows(self, peer: str) -> bool:
        return (
            peer == self.peer and time.monotonic() < self.deadline and self.attempts < 8
        )

    def qr(self, ssid: str, password: str, server: str) -> str:
        if not 1 <= len(ssid.encode()) <= 32 or not 8 <= len(password.encode()) <= 63:
            raise ValueError("Unsupported Wi-Fi credentials")
        if "\x00" in ssid or "\x00" in password:
            raise ValueError("Invalid Wi-Fi credentials")
        server = lan_address(server)
        return " ".join(
            (
                "pair",
                quote(ssid, safe=""),
                quote(password, safe=""),
                self.account,
                "1",
                server,
                str(1_000_000 + secrets.randbelow(9_000_000)),
                secrets.token_hex(5),
            )
        )

    async def handle(self, reader, writer) -> None:
        if self.attempts >= 8:
            raise ValueError("Enrollment attempt limit reached")
        self.attempts += 1
        connection = await F3Connection.accept(reader, writer)
        line = await connection.readline()
        try:
            parts = line.decode("ascii").split()
        except UnicodeError:
            _LOGGER.debug("Local enrollment rejected: reason=encoding")
            raise ValueError("Invalid enrollment encoding") from None
        if (
            len(line) > 512
            or len(parts) != 5
            or parts[0] != "dreg"
            or not 3 <= len(parts[1]) <= 30
            or not 1 <= len(parts[3]) <= 128
            or any(not 33 <= ord(c) <= 126 for part in parts for c in part)
        ):
            _LOGGER.debug("Local enrollment rejected: reason=framing")
            raise ValueError("Invalid enrollment framing")
        reason = None
        if not hmac.compare_digest(parts[2], self.account):
            reason = "qr_identifier"
        elif parts[4] != MODEL:
            reason = "model"
        elif self.identifier is not None and parts[1] != self.identifier:
            reason = "device_identity"
        if reason:
            _LOGGER.debug("Local enrollment rejected: reason=%s", reason)
            raise ValueError("Enrollment does not match the active QR")
        self.identifier = parts[1]
        self.device = Device(
            self.device.owner_id,
            parts[1],
            MODEL,
            parts[3],
            self.device.magic_token,
            self.device.sid_device,
            "-1",
        )
        response = (
            " ".join(
                (
                    "dreg",
                    self.device.owner_id,
                    parts[1],
                    MODEL,
                    parts[3],
                    self.device.magic_token,
                    self.device.sid_device,
                )
            )
            + "\n"
        )
        await connection.send(response.encode())
        self.registered.set()
        _LOGGER.debug("Local enrollment accepted: credential_origin=home_assistant")
