"""Unload must close active clients before waiting for server shutdown."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.motorola_nursery.bridge import RtspBridge
from custom_components.motorola_nursery.protocol import Credentials


@pytest.mark.asyncio
async def test_stop_closes_active_tunnel_and_forwarding_tasks(socket_enabled):
    receiving = asyncio.Event()
    cancelled = asyncio.Event()

    async def receive():
        receiving.set()
        try:
            await asyncio.Future()
        finally:
            cancelled.set()

    tunnel = AsyncMock()
    tunnel.receive.side_effect = receive
    credentials = Credentials(
        123456, b"abcdefghijklmnopqrst", b"test-token", "u", "p", "t"
    )
    bridge = RtspBridge("192.0.2.10", credentials, lambda err: None)
    with patch(
        "custom_components.motorola_nursery.bridge.MagicP2PTunnel.connect",
        AsyncMock(return_value=tunnel),
    ):
        await bridge.start()
        reader, writer = await asyncio.open_connection("127.0.0.1", bridge.port)
        try:
            await asyncio.wait_for(receiving.wait(), 1)
            await asyncio.wait_for(bridge.stop(), 2)
            assert cancelled.is_set()
            assert await reader.read() == b""
            tunnel.close.assert_awaited_once()
        finally:
            writer.close()
            await writer.wait_closed()
            await bridge.stop()
