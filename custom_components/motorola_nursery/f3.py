"""FePe V3 framing and ephemeral local session encryption."""

from __future__ import annotations

import asyncio
import secrets

from nacl.public import Box, PrivateKey, PublicKey

# Fixed wire-format obfuscation, shared by all V3 greetings. This is neither a
# camera credential nor a session key. The actual table is negotiated per socket.
HELLO_MASK = bytes.fromhex(
    "243f6a8885a308d313198a2e03707344a4093822299f31d0082efa98ec4e6c89452821e6"
    "38d01377be5466cf34e90c6cc0ac29b7c97c50dd3f84d5b5b54709179216d5d98979fb1b"
)
MAX_LINE = 65536


class F3Cipher:
    """Directional rolling transform with a negotiated 1024-byte table."""

    def __init__(self, table: bytes, index: int = 0) -> None:
        if len(table) != 1024 or not 0 <= index < 1024:
            raise ValueError("Invalid local cipher state")
        self._table = table
        self._index = index

    def transform(self, data: bytes, *, encode: bool = False) -> bytes:
        output = bytearray()
        for value in data:
            key = self._table[self._index]
            plain = value if encode else value ^ key
            output.append(value ^ key)
            self._index = (self._index + ((plain + key) | 1)) & 1023
        return bytes(output)


def transform_hello(data: bytes) -> bytes:
    """The greeting uses a fixed mask; session keys are never fixed."""
    if len(data) != 72:
        raise ValueError("Invalid local greeting")
    return bytes(a ^ b for a, b in zip(data, HELLO_MASK, strict=True))


class F3Connection:
    """One bounded encrypted stream, with serialized writes and private state."""

    def __init__(self, reader, writer, table: bytes) -> None:
        self.reader = reader
        self.writer = writer
        self._encoder = F3Cipher(table)
        self._decoder = F3Cipher(table)
        self._buffer = bytearray()
        self._send_lock = asyncio.Lock()

    @classmethod
    async def accept(cls, reader, writer) -> F3Connection:
        """Negotiate an independent session without contacting a vendor server."""
        async with asyncio.timeout(10):
            private = PrivateKey.generate()
            nonce = bytearray(secrets.token_bytes(24))
            nonce[0] &= 0x7B
            header = bytearray(21 + value % 235 for value in secrets.token_bytes(16))
            for index, value in enumerate(header):
                if value == ord("V"):
                    header[index] = index + 1
            position = secrets.randbelow(12)
            header[position : position + 4] = b"V3\0\0"
            greeting = bytes(header) + bytes(private.public_key) + bytes(nonce)
            writer.write(transform_hello(greeting))
            await writer.drain()
            reply = transform_hello(await reader.readexactly(72))
            if reply[:16] != greeting[:16] or reply[48:] != bytes(nonce):
                raise ValueError("Invalid local handshake response")
            table = secrets.token_bytes(1024)
            box = Box(private, PublicKey(reply[16:48]))
            writer.write(box.encrypt(table, bytes(nonce)).ciphertext)
            await writer.drain()
            return cls(reader, writer, table)

    async def send(self, data: bytes) -> None:
        async with self._send_lock:
            self.writer.write(self._encoder.transform(data, encode=True))
            await self.writer.drain()

    async def readline(self) -> bytes:
        while True:
            end = self._buffer.find(b"\n")
            if end >= 0:
                if end >= MAX_LINE:
                    raise ValueError("Local control line limit")
                line = bytes(self._buffer[: end + 1])
                del self._buffer[: end + 1]
                return line
            if len(self._buffer) >= MAX_LINE:
                raise ValueError("Local control line limit")
            data = await self.reader.read(4096)
            if not data:
                raise EOFError("Local control connection closed")
            self._buffer.extend(self._decoder.transform(data))

    def close(self) -> None:
        self.writer.close()
