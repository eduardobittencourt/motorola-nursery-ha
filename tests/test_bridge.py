"""Unload must close active clients before waiting for server shutdown."""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

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


@pytest.mark.parametrize("failure", ["receive", "send", "eof", "client_close"])
async def test_forwarding_failures_trigger_recovery_but_client_close_does_not(
    socket_enabled, failure
):
    async def pending_receive():
        await asyncio.Future()

    tunnel = AsyncMock()
    tunnel.receive.side_effect = pending_receive
    if failure == "receive":
        tunnel.receive.side_effect = ConnectionResetError("Synthetic camera reset")
    elif failure == "send":
        tunnel.send.side_effect = OSError("Synthetic send failure")
    elif failure == "eof":
        tunnel.receive.side_effect = None
        tunnel.receive.return_value = b""
    errors = Mock()
    credentials = Credentials(123456, b"synthetic-device", b"test-token", "u", "p", "t")
    bridge = RtspBridge("192.0.2.10", credentials, errors)
    with patch(
        "custom_components.motorola_nursery.bridge.MagicP2PTunnel.connect",
        AsyncMock(return_value=tunnel),
    ):
        await bridge.start()
        reader, writer = await asyncio.open_connection("127.0.0.1", bridge.port)
        try:
            if failure == "client_close":
                writer.write_eof()
            else:
                writer.write(b"synthetic request")
                await writer.drain()
            assert await asyncio.wait_for(reader.read(), 1) == b""
            await bridge.stop()
            assert bridge.active_connections == 0
            tunnel.close.assert_awaited_once()
            if failure == "client_close":
                errors.assert_not_called()
            else:
                errors.assert_called_once()
                assert isinstance(errors.call_args.args[0], (OSError, EOFError))
        finally:
            writer.close()
            await writer.wait_closed()
            await bridge.stop()
