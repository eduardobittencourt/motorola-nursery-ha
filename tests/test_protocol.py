"""Protocol tests independent from a Home Assistant installation."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import unittest
from pathlib import Path

import pytest

MODULE_PATH = (
    Path(__file__).parents[1] / "custom_components" / "motorola_nursery" / "protocol.py"
)
SPEC = importlib.util.spec_from_file_location("motorola_protocol", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
protocol = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = protocol
SPEC.loader.exec_module(protocol)


class CipherTest(unittest.TestCase):
    """Exercise state and TCP fragmentation behavior."""

    def test_round_trip_with_fragmented_prefix_and_payload(self) -> None:
        token = b"a-local-test-token"
        plaintext = b"OPTIONS rtsp://127.0.0.1/ RTSP/1.0\r\n\r\n" * 4
        encoded = protocol.MagicCipher(token).encode(plaintext)
        decoder = protocol.MagicCipher(token)
        fragments = [encoded[:3], encoded[3:11], encoded[11:29], encoded[29:]]
        self.assertEqual(
            b"".join(decoder.decode(part) for part in fragments), plaintext
        )

    def test_sid_and_handshake_shapes(self) -> None:
        credentials = protocol.Credentials(
            sid_user_id=123456,
            sid_device=b"abcdefghijklmnopqrst",
            magic_token=b"token-for-test-123456789012",
            rtsp_username="user",
            rtsp_password="password",
            access_token="access",
        )
        sid = protocol.generate_sid(credentials)
        request, request_sid = protocol.build_handshake(credentials)
        self.assertEqual(len(sid), 78)
        self.assertEqual(request_sid, sid)
        self.assertTrue(request.startswith(b"v002 888 06667 078 "))
        self.assertIn(sid, request)

        request, _ = protocol.build_handshake(credentials, target_port=8080)
        self.assertTrue(request.startswith(b"v002 888 08080 078 "))

    def test_handshake_rejects_invalid_target_port(self) -> None:
        credentials = protocol.Credentials(
            sid_user_id=123456,
            sid_device=b"abcdefghijklmnopqrst",
            magic_token=b"token-for-test-123456789012",
            rtsp_username="user",
            rtsp_password="password",
            access_token="access",
        )
        with self.assertRaisesRegex(ValueError, "Target port"):
            protocol.build_handshake(credentials, target_port=65536)


@pytest.mark.usefixtures("socket_enabled")
class TunnelTest(unittest.IsolatedAsyncioTestCase):
    """Exercise the handshake delimiter and bidirectional cipher state."""

    async def test_tunnel_round_trip(self) -> None:
        credentials = protocol.Credentials(
            sid_user_id=123456,
            sid_device=b"abcdefghijklmnopqrst",
            magic_token=b"token-for-test-123456789012",
            rtsp_username="user",
            rtsp_password="password",
            access_token="access",
        )
        received: list[bytes] = []
        requested_ports: list[bytes] = []

        async def fake_camera(
            reader: asyncio.StreamReader, writer: asyncio.StreamWriter
        ) -> None:
            handshake = await reader.readexactly(139)
            requested_ports.append(handshake.split()[2])
            sid = handshake.split()[4]
            writer.write(b"ok 0 dconn " + sid + b"\n")
            await writer.drain()
            decoder = protocol.MagicCipher(credentials.magic_token)
            encoder = protocol.MagicCipher(credentials.magic_token)
            while not (plain := decoder.decode(await reader.read(4096))):
                pass
            received.append(plain)
            writer.write(encoder.encode(b"RTSP/1.0 200 OK\r\n\r\n"))
            await writer.drain()
            writer.close()
            await writer.wait_closed()

        server = await asyncio.start_server(fake_camera, "127.0.0.1", 0)
        original_port = protocol.CAMERA_PORT
        protocol.CAMERA_PORT = server.sockets[0].getsockname()[1]
        try:
            tunnel = await protocol.MagicP2PTunnel.connect(
                "127.0.0.1", credentials, target_port=8080
            )
            await tunnel.send(b"OPTIONS rtsp://camera/ RTSP/1.0\r\n\r\n")
            self.assertEqual(await tunnel.receive(), b"RTSP/1.0 200 OK\r\n\r\n")
            await tunnel.close()
        finally:
            protocol.CAMERA_PORT = original_port
            server.close()
            await server.wait_closed()
        self.assertEqual(received, [b"OPTIONS rtsp://camera/ RTSP/1.0\r\n\r\n"])
        self.assertEqual(requested_ports, [b"08080"])


if __name__ == "__main__":
    unittest.main()
