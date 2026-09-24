"""5GenCare MagicP2P transport used by supported Motorola cameras."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import hashlib
import hmac
import os
import uuid

CAMERA_PORT = 77
INTERNAL_RTSP_PORT = 6667
CONNECT_TIMEOUT = 8


@dataclass(frozen=True, slots=True)
class Credentials:
    """Technical credentials required by the local camera tunnel."""

    sid_user_id: int
    sid_device: bytes
    magic_token: bytes
    rtsp_username: str
    rtsp_password: str
    access_token: str

    def validate(self) -> None:
        """Reject malformed data before opening a network connection."""
        if self.sid_user_id < 0 or self.sid_user_id > 0xFFFFFFFF:
            raise ValueError("SID user ID must fit in an unsigned 32-bit integer")
        if not 3 <= len(self.sid_device) <= 20:
            raise ValueError("SID device value must contain 3 to 20 bytes")
        if not 3 <= len(self.magic_token) <= 27:
            raise ValueError("MagicP2P token must contain 3 to 27 bytes")
        if not self.rtsp_username or not self.rtsp_password or not self.access_token:
            raise ValueError("RTSP credentials and access token are required")


class MagicCipher:
    """Stateful byte transform used after the MagicP2P handshake."""

    def __init__(self, token: bytes) -> None:
        if not 1 <= len(token) < 254:
            raise ValueError("Invalid token length")
        self._token = token
        self._prefix = bytearray()
        self._key: bytearray | None = None
        self._index = 0

    def _initialize(self, prefix: bytes | bytearray) -> None:
        previous = 0xAA
        key = bytearray()
        for token_byte, random_byte in zip(self._token, prefix, strict=False):
            previous ^= (token_byte >> 1) ^ ((random_byte & 0x7F) << 1)
            key.append(previous)
        self._key = key
        self._index = prefix[len(self._token)] % len(self._token)

    def encode(self, data: bytes) -> bytes:
        """Encode a chunk; the first call prepends the random cipher state."""
        output = bytearray()
        if self._key is None:
            # The native implementation generates bytes in the inclusive range
            # 21..255 and stores token_length + 1 as the initial key index.
            prefix = bytes(21 + value % 235 for value in os.urandom(len(self._token)))
            prefix += bytes([len(self._token) + 1])
            self._initialize(prefix)
            output.extend(prefix)
        output.extend(self._transform(data, encode=True))
        return bytes(output)

    def decode(self, data: bytes) -> bytes:
        """Decode a chunk, accepting a cipher prefix split across TCP reads."""
        if self._key is None:
            needed = len(self._token) + 1 - len(self._prefix)
            consumed = min(len(data), needed)
            self._prefix.extend(data[:consumed])
            data = data[consumed:]
            if len(self._prefix) <= len(self._token):
                return b""
            self._initialize(self._prefix)
        return self._transform(data, encode=False)

    def _transform(self, data: bytes, *, encode: bool) -> bytes:
        assert self._key is not None
        output = bytearray()
        for value in data:
            key_byte = self._key[self._index]
            plain = value if encode else value ^ key_byte
            output.append(value ^ key_byte)
            self._index = (
                self._index + ((plain + key_byte) | 1)
            ) % len(self._token)
        return bytes(output)


def generate_sid(credentials: Credentials) -> bytes:
    """Generate the 78-byte v1 device session identifier."""
    credentials.validate()
    identifier = f"{credentials.sid_user_id:08x}".encode()
    device = credentials.sid_device
    token = credentials.magic_token
    key = (
        identifier
        + device.ljust(20, b" ")
        + token.ljust(27, b" ")
        + device.ljust(20, b" ")
    )[:32]
    digest = hmac.new(key, device, hashlib.sha256).hexdigest().encode()
    return (identifier + device[:3] + token[:3] + digest).lower()


def build_handshake(credentials: Credentials) -> tuple[bytes, bytes]:
    """Build a connection request and return it with the expected SID."""
    sid = generate_sid(credentials)
    client_id = str(uuid.uuid4()).encode()
    request = (
        b"v002 888 "
        + f"{INTERNAL_RTSP_PORT:05d} {len(sid):03d} ".encode()
        + sid
        + f" {len(client_id):04d} ".encode()
        + client_id
    )
    return request, sid


class MagicP2PTunnel:
    """One authenticated, encrypted TCP tunnel to the internal RTSP server."""

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        token: bytes,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._encoder = MagicCipher(token)
        self._decoder = MagicCipher(token)

    @classmethod
    async def connect(cls, host: str, credentials: Credentials) -> MagicP2PTunnel:
        """Open and authenticate a local camera connection."""
        credentials.validate()
        async with asyncio.timeout(CONNECT_TIMEOUT):
            reader, writer = await asyncio.open_connection(host, CAMERA_PORT)
            try:
                request, sid = build_handshake(credentials)
                writer.write(request)
                await writer.drain()
                response = await reader.readexactly(
                    len(b"ok 0 dconn ") + len(sid) + 1
                )
                if (
                    response[:-1] != b"ok 0 dconn " + sid
                    or response[-1:] not in (b"\n", b"\r", b"\0", b" ")
                ):
                    raise ConnectionError("Camera rejected the MagicP2P handshake")
            except BaseException:
                writer.close()
                await writer.wait_closed()
                raise
        return cls(reader, writer, credentials.magic_token)

    async def send(self, data: bytes) -> None:
        """Encode and forward plaintext bytes to the camera."""
        self._writer.write(self._encoder.encode(data))
        await self._writer.drain()

    async def receive(self) -> bytes:
        """Receive and decode at least one plaintext chunk."""
        while encrypted := await self._reader.read(65536):
            if plain := self._decoder.decode(encrypted):
                return plain
        return b""

    async def close(self) -> None:
        """Close the camera transport."""
        self._writer.close()
        await self._writer.wait_closed()
