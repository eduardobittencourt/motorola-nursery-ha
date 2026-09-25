"""Real stream framing tests against a synthetic in-process vendor server."""

import asyncio
import ssl
from unittest.mock import patch

import pytest

from custom_components.motorola_nursery.cloud import (
    AuthenticationError,
    CloudClient,
    CloudError,
    Session,
    atom,
    parse_devices,
)


@pytest.mark.asyncio
async def test_login_resume_devices_and_idle_keepalive(socket_enabled):
    observed = []
    peer_done = asyncio.Event()

    async def server(reader, writer):
        try:
            observed.append(await reader.readline())
            writer.write(b"v3_otp 123456 opaque 9.moto.5gencare.com\n")
            await writer.drain()
            writer.write(b"pi")
            await writer.drain()
            await asyncio.sleep(0)
            writer.write(b"ng\n")
            await writer.drain()
            assert await reader.readline() == b"pong\n"
            observed.append(await reader.readline())
            writer.write(
                b"v3_loginset 123456 synthetic-token unused-long-token "
                b"1234567 9.moto.5gencare.com\n"
            )
            await writer.drain()
            observed.append(await reader.readline())
            writer.write(
                b"v3_session 123456 rotated-test-token 1234567 "
                b"9.moto.5gencare.com\nv3_unrelated 1\n"
            )
            await writer.drain()
            observed.append(await reader.readline())
            writer.write(
                b"v3_dlist 1 123456 camera-identifier VM65 Nursery%20Test "
                b"test-magic-token abcdefghijklmnopqrst -1\n"
            )
            await writer.drain()
            await reader.read()
        finally:
            writer.close()
            await writer.wait_closed()
            peer_done.set()

    listener = await asyncio.start_server(server, "127.0.0.1", 0)
    address = listener.sockets[0].getsockname()
    open_connection = asyncio.open_connection

    async def connect(*args, **kwargs):
        assert isinstance(kwargs["ssl"], ssl.SSLContext)
        assert kwargs["ssl"].verify_mode == ssl.CERT_REQUIRED
        assert kwargs["server_hostname"] == "9.moto.5gencare.com"
        return await open_connection(*address)

    client = CloudClient(ssl.create_default_context())
    try:
        with patch(
            "custom_components.motorola_nursery.cloud.asyncio.open_connection", connect
        ):
            await client.connect()
        challenge = await client.request_code("SYNTHETICUUID", "owner@example.test")
        await asyncio.sleep(
            0.01
        )  # The reader answers ping while no request is running.
        session = await client.submit_code(
            challenge, "SYNTHETICUUID", "owner@example.test", "123456"
        )
        renewed = await client.resume(session)
        devices = await client.devices()
        assert renewed.token == "rotated-test-token"
        assert client.session == renewed
        assert devices[0].name == "Nursery Test"
        assert "test-magic-token" not in repr(devices[0])
        assert "rotated-test-token" not in repr(renewed)
    finally:
        await client.close()
        await asyncio.wait_for(peer_done.wait(), 2)
        listener.close()
        await listener.wait_closed()
    assert observed[0] == b"v3_otp SYNTHETICUUID email owner@example.test 6\n"
    assert (
        observed[1]
        == b"v3_loginset 123456 SYNTHETICUUID email owner@example.test 123456\n"
    )


@pytest.mark.asyncio
async def test_session_rejection_contains_no_payload():
    client = CloudClient(ssl.create_default_context())
    from unittest.mock import AsyncMock

    client._exchange = AsyncMock(return_value=["-10"])
    with pytest.raises(AuthenticationError, match="Session rejected"):
        await client.resume(Session("123456", "private-token", "1234567", client.host))
    assert client.session is None


def test_device_framing_and_injection():
    row = ["123456", "opaque", "VM65", "Nursery", "test-token", "test-device", "-1"]
    assert len(parse_devices(["2", *row, *row])) == 2
    for fields in [["-1"], ["99"], ["2", *row], ["1", *row, "extra"]]:
        with pytest.raises(CloudError):
            parse_devices(fields)
    for value in ["a@example.test\nv3_dlist", "white space", "a\x00b"]:
        with pytest.raises(ValueError):
            atom(value)
