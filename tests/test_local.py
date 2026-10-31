"""Real loopback F3 cameras: identity, readings, events and disconnects."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest
from nacl.public import Box, PrivateKey, PublicKey

from custom_components.motorola_nursery.f3 import (
    F3Cipher,
    F3Connection,
    transform_hello,
)
from custom_components.motorola_nursery.local import (
    LocalControlServer,
    LocalEventListener,
    LocalTelemetryClient,
    Registration,
)
from custom_components.motorola_nursery.protocol import Credentials
from custom_components.motorola_nursery.telemetry import TelemetryError

CREDENTIALS = Credentials(
    123456, b"synthetic-device", b"synthetic-token", "user", "pass", "access"
)
CAPS = (
    b"caplist 3 temperature_reading r int -200 500 wifi_signal r int 0 100 "
    b"wifi_ssid r str 1 64\r\n"
)


async def camera(port, registration=b"dev 123456 synthetic-token 1.0.0\n"):
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    greeting = transform_hello(await reader.readexactly(72))
    assert b"V3" in greeting[:16]
    private = PrivateKey.generate()
    writer.write(
        transform_hello(greeting[:16] + bytes(private.public_key) + greeting[48:])
    )
    await writer.drain()
    box = Box(private, PublicKey(greeting[16:48]))
    table = box.decrypt(await reader.readexactly(1040), greeting[48:])
    connection = F3Connection(reader, writer, table)
    await connection.send(registration)
    return connection


async def connected(port, *, acknowledge=True):
    connection = await camera(port)
    reply = (await connection.readline()).decode().split()
    assert reply[:2] == ["dev", "2"]
    clock = datetime.strptime(reply[2], "%m%d%H%M%Y.%S")
    assert abs((clock.replace(tzinfo=UTC) - datetime.now(UTC)).total_seconds()) < 10
    assert await connection.readline() == (
        b"magicp2p 1 synthetic-device synthetic-device\n"
    )
    if acknowledge:
        await connection.send(b"magicp2p 1\n")
    return connection


async def test_local_read_events_and_reconnect(socket_enabled):
    server = LocalControlServer(0)
    registration = await server.register("camera-one", lambda: CREDENTIALS)
    client = LocalTelemetryClient(registration)
    events, states = [], []
    listener = LocalEventListener(registration, events.append, states.append)
    listener.start()
    await asyncio.sleep(0)
    assert states == [False]
    try:
        for _ in range(2):
            connection = await connected(server.port)

            async def respond(connection=connection):
                assert await connection.readline() == b"caplist\n"
                await connection.send(CAPS)
                assert await connection.readline() == (
                    b"get 2 temperature_reading wifi_signal\n"
                )
                await connection.send(
                    b"notify synthetic-token motiondetect synthetic-event\n"
                    b"notify wrong-token sounddetect ignored-event\n"
                    b"get 2 temperature_reading 239 wifi_signal 71\r\n"
                )
                assert await connection.readline() == b"notify 1 1\n"
                # Subsequent polls reuse capabilities on this socket.
                assert await connection.readline() == (
                    b"get 2 temperature_reading wifi_signal\n"
                )
                await connection.send(b"get 2 temperature_reading 240 wifi_signal 70\n")

            task = asyncio.create_task(respond())
            with patch(
                "asyncio.open_connection", side_effect=AssertionError("Cloud forbidden")
            ):
                data = await client.async_read(CREDENTIALS)
                second = await client.async_read(CREDENTIALS)
            await task
            assert second.values == {"temperature_reading": 240, "wifi_signal": 70}
            assert data.values == {"temperature_reading": 239, "wifi_signal": 71}
            assert len(data.capabilities) == 2
            connection.close()
            await connection.writer.wait_closed()
            await asyncio.sleep(0.01)
        assert len(events) == 1  # Replayed detection is deduplicated across sockets.
        assert events[0].event_type == "motion"
        assert True in states
    finally:
        await listener.stop()
        await server.unregister("camera-one")
    assert not server._tasks
    assert not registration.ready.is_set()


@pytest.mark.parametrize(
    "line",
    [
        b"dev 123456 private-wrong-token 1.0.0\n",
        b"dev 999999 synthetic-token 1.0.0\n",
        b"dev malformed\n",
        b"dev 999999999999999999999 synthetic-token 1.0.0\n",
    ],
)
async def test_unknown_camera_is_rejected_without_secret_logs(
    socket_enabled, caplog, line
):
    server = LocalControlServer(0)
    await server.register("camera-one", lambda: CREDENTIALS)
    try:
        connection = await camera(server.port, line)
        with pytest.raises(EOFError):
            await asyncio.wait_for(connection.readline(), 1)
        connection.close()
        await connection.writer.wait_closed()
        assert "private-wrong-token" not in caplog.text
        assert "synthetic-token" not in caplog.text
    finally:
        await server.unregister("camera-one")


async def test_listener_shutdown_cancels_partial_handshakes(socket_enabled):
    server = LocalControlServer(0)
    await server.register("one", lambda: CREDENTIALS)
    await server.register("two", lambda: CREDENTIALS)
    reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
    await reader.readexactly(72)
    await server.unregister("one")
    assert server._server is not None
    await asyncio.wait_for(server.unregister("two"), 2)
    assert await reader.read() == b""
    writer.close()
    await writer.wait_closed()
    assert not server._tasks


async def test_missing_camera_never_falls_back_to_cloud():
    client = LocalTelemetryClient(Registration(lambda: CREDENTIALS))
    with (
        patch("custom_components.motorola_nursery.local.TIMEOUT", 0.01),
        patch("asyncio.open_connection", side_effect=AssertionError("Cloud forbidden")),
        pytest.raises(TelemetryError, match="Local camera"),
    ):
        await client.async_read(CREDENTIALS)


@pytest.mark.parametrize(
    "method,args",
    [
        ("async_set", ("video_brightness", 1)),
        ("async_list_songs", ()),
        ("async_play", ("Song.mp3",)),
        ("async_stop", ()),
        ("async_ptz", ("pan", "left")),
    ],
)
async def test_unvalidated_controls_do_not_send_cloud_or_device_commands(method, args):
    client = LocalTelemetryClient(Registration(lambda: CREDENTIALS))
    with (
        patch("asyncio.open_connection", side_effect=AssertionError("Cloud forbidden")),
        pytest.raises(TelemetryError, match="not validated"),
    ):
        await getattr(client, method)(CREDENTIALS, *args)


async def test_cancelled_getter_closes_socket_to_discard_late_responses(socket_enabled):
    server = LocalControlServer(0)
    registration = await server.register("one", lambda: CREDENTIALS)
    connection = await connected(server.port)
    client = LocalTelemetryClient(registration)
    task = asyncio.create_task(client.async_read(CREDENTIALS))
    try:
        assert await connection.readline() == b"caplist\n"
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        with pytest.raises(EOFError):
            await asyncio.wait_for(connection.readline(), 1)
    finally:
        connection.close()
        await connection.writer.wait_closed()
        await server.unregister("one")


def test_cipher_rejects_invalid_sizes_and_preserves_fragmented_state():
    for key, index in ((b"short", 0), (bytes(1024), 1024)):
        with pytest.raises(ValueError):
            F3Cipher(key, index)
    with pytest.raises(ValueError):
        transform_hello(bytes(71))
    table = bytes(range(256)) * 4
    encoder, decoder = F3Cipher(table, 731), F3Cipher(table, 731)
    plaintext = b"caplist\nget 1 temperature_reading\n" * 60
    wire = encoder.transform(plaintext, encode=True)
    assert (
        b"".join(decoder.transform(wire[i : i + 3]) for i in range(0, len(wire), 3))
        == plaintext
    )


async def test_encrypted_line_limit_is_enforced():
    reader = asyncio.StreamReader()
    writer = Mock()
    connection = F3Connection(reader, writer, bytes(1024))
    reader.feed_data(bytes(65536))
    with pytest.raises(ValueError, match="line limit"):
        await connection.readline()


async def test_late_connection_gets_full_command_deadline():
    registration = Registration(lambda: CREDENTIALS)
    peer = Mock(
        closed=False,
        command_lock=asyncio.Lock(),
        responses=asyncio.Queue(),
    )
    client = LocalTelemetryClient(registration)

    async def connect_later():
        await asyncio.sleep(0.12)
        registration.peer = peer
        registration.ready.set()

    task = asyncio.create_task(connect_later())
    with patch("custom_components.motorola_nursery.local.TIMEOUT", 0.2):
        async with client._session(CREDENTIALS):
            await asyncio.sleep(0.12)
    await task
    peer.close.assert_not_called()


async def test_malformed_reply_invalidates_persistent_session(socket_enabled):
    server = LocalControlServer(0)
    registration = await server.register("one", lambda: CREDENTIALS)
    connection = await connected(server.port)
    client = LocalTelemetryClient(registration)
    task = asyncio.create_task(client.async_read(CREDENTIALS))
    try:
        assert await connection.readline() == b"caplist\n"
        await connection.send(b"caplist invalid\n")
        with pytest.raises(TelemetryError):
            await task
        with pytest.raises(EOFError):
            await asyncio.wait_for(connection.readline(), 1)
    finally:
        connection.close()
        await connection.writer.wait_closed()
        await server.unregister("one")


async def test_setup_ack_required_before_getters(socket_enabled):
    server = LocalControlServer(0)
    registration = await server.register("one", lambda: CREDENTIALS)
    events = []
    registration.event_callbacks.add(events.append)
    client = LocalTelemetryClient(registration)
    connection = await connected(server.port, acknowledge=False)
    task = asyncio.create_task(client.async_read(CREDENTIALS))
    try:
        await connection.send(b"ping\n")
        assert await connection.readline() == b"pong\n"
        await connection.send(b"notify synthetic-token motiondetect setup-event\n")
        assert await connection.readline() == b"notify 1 1\n"
        assert len(events) == 1
        assert not registration.ready.is_set()
        assert not task.done()
        await connection.send(b"magicp2p 1\n")
        assert await connection.readline() == b"caplist\n"
        await connection.send(CAPS)
        assert (await connection.readline()).startswith(b"get 2 ")
        await connection.send(b"get 2 temperature_reading 240 wifi_signal 70\n")
        assert (await task).values["temperature_reading"] == 240
    finally:
        task.cancel()
        connection.close()
        await connection.writer.wait_closed()
        await server.unregister("one")


@pytest.mark.parametrize("acknowledgement", [None, b"magicp2p 0\n"])
async def test_missing_or_rejected_setup_never_becomes_ready(
    socket_enabled, acknowledgement
):
    server = LocalControlServer(0)
    registration = await server.register("one", lambda: CREDENTIALS)
    try:
        with patch(
            "custom_components.motorola_nursery.local.INITIALIZATION_TIMEOUT", 0.1
        ):
            connection = await connected(server.port, acknowledge=False)
            if acknowledgement is not None:
                await connection.send(acknowledgement)
            with pytest.raises(EOFError):
                await asyncio.wait_for(connection.readline(), 1)
            assert not registration.ready.is_set()
            connection.close()
            await connection.writer.wait_closed()
    finally:
        await server.unregister("one")


async def test_shutdown_aborts_stalled_transports_within_deadline():
    closed = asyncio.Event()
    transport_server = Mock(spec=asyncio.Server)
    transport_server.wait_closed = AsyncMock(side_effect=closed.wait)
    transport_server.abort_clients.side_effect = closed.set
    server = LocalControlServer(0)
    server._server = transport_server
    with patch("custom_components.motorola_nursery.local.SHUTDOWN_TIMEOUT", 0.01):
        await asyncio.wait_for(server._stop(), 0.5)
    transport_server.close.assert_called_once()
    transport_server.abort_clients.assert_called_once()
    assert server._server is None


@pytest.mark.parametrize("ambiguous", [False, True])
async def test_multiple_entries_require_unique_registration(socket_enabled, ambiguous):
    second_credentials = replace(
        CREDENTIALS,
        sid_device=b"second-device",
        magic_token=CREDENTIALS.magic_token if ambiguous else b"second-token",
    )
    server = LocalControlServer(0)
    first = await server.register("one", lambda: CREDENTIALS)
    second = await server.register("two", lambda: second_credentials)
    connection = None
    try:
        if ambiguous:
            connection = await camera(server.port)
            with pytest.raises(EOFError):
                await asyncio.wait_for(connection.readline(), 1)
            assert first.peer is None
            assert not first.ready.is_set()
        else:
            connection = await connected(server.port)
            await asyncio.wait_for(first.ready.wait(), 1)
            assert first.peer is not None
        assert second.peer is None
        assert not second.ready.is_set()
    finally:
        if connection:
            connection.close()
            await connection.writer.wait_closed()
        await server.unregister("one")
        await server.unregister("two")
