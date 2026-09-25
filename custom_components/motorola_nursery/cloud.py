"""Authenticated 5GenCare text protocol; secrets never appear in exceptions."""

from __future__ import annotations

import asyncio
import re
import ssl
from contextlib import suppress
from dataclasses import dataclass, field
from urllib.parse import unquote

DEFAULT_HOST = "9.moto.5gencare.com"
PORT = 3388
MAX_LINE = 65536
TIMEOUT = 15


class CloudError(Exception):
    """Malformed or rejected cloud operation."""


class AuthenticationError(CloudError):
    """The session or email code was rejected."""


def atom(value: str) -> str:
    """Prevent protocol injection, including whitespace and non-ASCII input."""
    if not value or any(ord(char) < 33 or ord(char) > 126 for char in value):
        raise ValueError("Invalid protocol field")
    return value


def vendor_host(value: str) -> str:
    """Only follow routing responses within the vendor's camera domain."""
    if not re.fullmatch(r"[a-z0-9-]+\.moto\.5gencare\.com", value):
        raise CloudError("Unexpected authentication server")
    return value


@dataclass(frozen=True, slots=True)
class Session:
    """Replace the saved token after every successful session resumption."""

    user_id: str = field(repr=False)
    token: str = field(repr=False)
    session_id: str = field(repr=False)
    host: str

    def as_dict(self) -> dict[str, str]:
        return {
            "user_id": self.user_id,
            "token": self.token,
            "session_id": self.session_id,
            "host": self.host,
        }

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> Session:
        return cls(
            atom(data["user_id"]),
            atom(data["token"]),
            atom(data["session_id"]),
            vendor_host(data["host"]),
        )


@dataclass(frozen=True, slots=True)
class Challenge:
    """OTP request information, used only while the config flow is active."""

    user_id: str = field(repr=False)
    host: str


@dataclass(frozen=True, slots=True)
class Device:
    """Device credentials from the authenticated list; seven fields per row."""

    owner_id: str = field(repr=False)
    identifier: str = field(repr=False)
    model: str
    encoded_name: str = field(repr=False)
    magic_token: str = field(repr=False)
    sid_device: str = field(repr=False)
    trailing_field: str

    @property
    def name(self) -> str:
        return unquote(self.encoded_name) or "Motorola camera"


def parse_devices(fields: list[str]) -> list[Device]:
    try:
        count = int(fields[0])
    except (IndexError, ValueError):
        raise CloudError("Invalid device count") from None
    if not 0 <= count <= 32 or len(fields) != 1 + count * 7:
        raise CloudError("Unrecognized device list framing")
    result = []
    for index in range(count):
        row = fields[1 + index * 7 : 8 + index * 7]
        if (
            not row[0].isdigit()
            or not 0 <= int(row[0]) <= 0xFFFFFFFF
            or not 3 <= len(row[4]) <= 27
            or not 3 <= len(row[5]) <= 20
        ):
            raise CloudError("Invalid device credentials")
        result.append(Device(*row))
    return result


class CloudClient:
    """One serialized session; a reader answers keepalives during UI code entry."""

    def __init__(self, context: ssl.SSLContext, host: str = DEFAULT_HOST) -> None:
        self.host = vendor_host(host)
        self.session: Session | None = None
        self._context = context
        self._writer: asyncio.StreamWriter | None = None
        self._reader_task: asyncio.Task | None = None
        self._messages: asyncio.Queue[list[str] | Exception] = asyncio.Queue(64)
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        if self._writer is not None:
            raise RuntimeError("Client is already connected")
        async with asyncio.timeout(TIMEOUT):
            reader, self._writer = await asyncio.open_connection(
                self.host,
                PORT,
                ssl=self._context,
                server_hostname=self.host,
                limit=MAX_LINE,
            )
        self._reader_task = asyncio.create_task(self._receive(reader))

    async def _receive(self, reader: asyncio.StreamReader) -> None:
        try:
            while True:
                raw = await reader.readline()
                if not raw:
                    raise ConnectionError("Cloud connection closed")
                if len(raw) > MAX_LINE or not raw.endswith(b"\n"):
                    raise CloudError("Invalid protocol frame")
                parts = raw.decode("ascii").split()
                if parts == ["ping"]:
                    if self._writer is not None:
                        self._writer.write(b"pong\n")
                        await self._writer.drain()
                elif parts:
                    self._messages.put_nowait(parts)
        except asyncio.CancelledError:
            raise
        except (OSError, ValueError, CloudError, asyncio.QueueFull):
            if self._messages.full():
                self._messages.get_nowait()
            self._messages.put_nowait(ConnectionError("Cloud connection closed"))

    async def close(self) -> None:
        if self._reader_task is not None:
            self._reader_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._reader_task
            self._reader_task = None
        if self._writer is not None:
            self._writer.close()
            with suppress(OSError, TimeoutError):
                async with asyncio.timeout(5):
                    await self._writer.wait_closed()
            self._writer = None

    async def _exchange(self, command: str, *fields: str) -> list[str]:
        if self._writer is None:
            raise ConnectionError("Client is not connected")
        message = " ".join([atom(command), *(atom(value) for value in fields)]) + "\n"
        async with asyncio.timeout(TIMEOUT):
            self._writer.write(message.encode("ascii"))
            await self._writer.drain()
            for _ in range(128):
                reply = await self._messages.get()
                if isinstance(reply, Exception):
                    raise reply
                if reply[0] == command:
                    return reply[1:]
            raise CloudError("Too many unrelated protocol frames")

    async def request_code(self, login_uuid: str, email: str) -> Challenge:
        """Send an email only following an explicit UI submission."""
        async with self._lock:
            fields = await self._exchange("v3_otp", login_uuid, "email", email, "6")
            if len(fields) != 3 or not fields[0].isdigit():
                raise CloudError("Email code request was not accepted")
            return Challenge(fields[0], vendor_host(fields[2]))

    async def submit_code(
        self, challenge: Challenge, login_uuid: str, email: str, code: str
    ) -> Session:
        if not re.fullmatch(r"[0-9]{6}", code):
            raise ValueError("Expected a six-digit email code")
        if challenge.host != self.host:
            raise CloudError("Incorrect challenge server")
        async with self._lock:
            fields = await self._exchange(
                "v3_loginset", challenge.user_id, login_uuid, "email", email, code
            )
            if fields and fields[0].startswith("-"):
                raise AuthenticationError("Email code rejected")
            if len(fields) != 5 or fields[0] != challenge.user_id:
                raise CloudError("Unexpected login response")
            self.session = Session(
                fields[0], atom(fields[1]), atom(fields[3]), vendor_host(fields[4])
            )
            return self.session

    async def resume(self, session: Session) -> Session:
        if session.host != self.host:
            raise CloudError("Incorrect session server")
        async with self._lock:
            fields = await self._exchange(
                "v3_session", session.user_id, session.token, session.session_id
            )
            if fields and fields[0].startswith("-"):
                raise AuthenticationError("Session rejected")
            if len(fields) != 4 or fields[0] != session.user_id:
                raise CloudError("Unexpected session response")
            self.session = Session(
                fields[0], atom(fields[1]), atom(fields[2]), vendor_host(fields[3])
            )
            return self.session

    async def devices(self) -> list[Device]:
        if self.session is None:
            raise AuthenticationError("Authenticate before listing devices")
        async with self._lock:
            return parse_devices(await self._exchange("v3_dlist"))
