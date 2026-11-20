"""Synthetic peers for QR enrollment, clock isolation and resource cleanup."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from urllib.parse import unquote

import pytest

from custom_components.motorola_nursery.bootstrap import (
    MODEL,
    LocalClockServer,
    LocalEnrollment,
    lan_address,
)
from tests.test_local import camera


@pytest.mark.parametrize(
    "address", ["localhost", "8.8.8.8", "127.0.0.1", "::1", "10.0.0.1:4400"]
)
def test_pairing_requires_explicit_private_ipv4(address):
    with pytest.raises(ValueError):
        lan_address(address)


def test_qr_credentials_are_fresh_and_wifi_is_uri_encoded():
    first, second = LocalEnrollment("192.168.1.2"), LocalEnrollment("192.168.1.2")
    parts = first.qr("Nursery & café", "example password", "192.168.1.3").split()
    assert len(parts) == 8
    assert [unquote(v) for v in parts[1:3]] == ["Nursery & café", "example password"]
    assert parts[3] == first.account
    assert parts[4:6] == ["1", "192.168.1.3"]
    assert len(parts[7]) == 10
    assert first.device.owner_id != first.account
    assert len(first.device.owner_id) == 6
    assert first.credentials.sid_user_id == int(first.device.owner_id)
    assert first.credentials != second.credentials
    assert first.credentials.magic_token not in repr(first).encode()
    for ssid, password in [
        ("", "password"),
        ("é" * 17, "password"),
        ("test", "short"),
        ("test", "p" * 64),
        ("a\x00b", "password"),
    ]:
        with pytest.raises(ValueError):
            first.qr(ssid, password, "192.168.1.3")


async def exchange(port, payload):
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    try:
        writer.write(payload)
        await writer.drain()
        return await asyncio.wait_for(reader.read(), 1)
    finally:
        writer.close()
        await writer.wait_closed()


async def test_clock_exact_request_source_isolation_shared_lifecycle(socket_enabled):
    server = LocalClockServer(0)
    await server.register("one", "127.0.0.1")
    await server.register("two", "192.0.2.2")
    try:
        response = await exchange(server.port, b"config\n")
        fields = response.decode().split()
        assert fields[0] == "config" and fields[2] == "false"
        clock = datetime.strptime(fields[1], "%m%d%H%M%Y.%S").replace(tzinfo=UTC)
        assert abs((clock - datetime.now(UTC)).total_seconds()) < 5
        assert await exchange(server.port, b"shell\n") == b""
        assert await exchange(server.port, b"x" * 5000 + b"\n") == b""
        await server.unregister("one")
        assert server.server is not None
        assert await exchange(server.port, b"config\n") == b""
    finally:
        await server.unregister("two")
    assert server.server is None
    assert not server.tasks


async def test_clock_cancels_stalled_clients_on_last_unregister(socket_enabled):
    server = LocalClockServer(0)
    await server.register("one", "127.0.0.1")
    reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
    try:
        await asyncio.sleep(0)
        await asyncio.wait_for(server.unregister("one"), 1)
        assert await reader.read() == b""
        assert not server.tasks
    finally:
        writer.close()
        await writer.wait_closed()


async def test_enrollment_returns_generated_credentials_binds_one_device(
    socket_enabled,
):
    server = LocalEnrollment("127.0.0.1", 0)
    await server.start()
    try:
        request = f"dreg synthetic-id {server.account} Test%20camera {MODEL}\n".encode()
        connection = await camera(server.port, request)
        try:
            parts = (await connection.readline()).decode().split()
            assert parts == [
                "dreg",
                server.device.owner_id,
                "synthetic-id",
                MODEL,
                "Test%20camera",
                server.device.magic_token,
                server.device.sid_device,
            ]
            assert server.registered.is_set()
            assert server.device.name == "Test camera"
        finally:
            connection.close()
            await connection.writer.wait_closed()
        other = await camera(
            server.port, request.replace(b"synthetic-id", b"other-device")
        )
        try:
            with pytest.raises(EOFError):
                await other.readline()
            assert server.device.identifier == "synthetic-id"
        finally:
            other.close()
            await other.writer.wait_closed()
    finally:
        await server.stop()
    assert not server.tasks


@pytest.mark.parametrize("field", ["account", "model", "command", "encoding", "size"])
async def test_enrollment_rejects_wrong_qr_and_unsupported_requests(
    socket_enabled, field, caplog
):
    import logging

    caplog.set_level(
        logging.DEBUG, logger="custom_components.motorola_nursery.bootstrap"
    )
    server = LocalEnrollment("127.0.0.1", 0)
    await server.start()
    request = f"dreg synthetic-id {server.account} Test {MODEL}\n".encode()
    if field == "account":
        request = request.replace(server.account.encode(), b"000000000")
    elif field == "model":
        request = request.replace(MODEL.encode(), b"OtherModel")
    elif field == "command":
        request = request.replace(b"dreg", b"reset")
    elif field == "encoding":
        request = b"\xff\n"
    else:
        request = b"x" * 600 + b"\n"
    connection = await camera(server.port, request)
    try:
        with pytest.raises(EOFError):
            await connection.readline()
        assert not server.registered.is_set()
        assert "Local enrollment rejected: reason=" in caplog.text
        assert server.account not in caplog.text
        assert "synthetic-id" not in caplog.text
    finally:
        connection.close()
        await connection.writer.wait_closed()
        await server.stop()


async def test_enrollment_expiry_attempt_cap_and_stalled_handshake_cleanup(
    socket_enabled,
):
    server = LocalEnrollment("127.0.0.1", 0)
    server.attempts = 8
    assert not server.allows("127.0.0.1")
    server.attempts = 0
    server.deadline = 0
    assert not server.allows("127.0.0.1")
    server.deadline = float("inf")
    assert not server.allows("192.0.2.2")
    await server.start()
    reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
    try:
        assert len(await reader.readexactly(72)) == 72
        await asyncio.wait_for(server.stop(), 1)
        assert await reader.read() == b""
        assert not server.tasks
    finally:
        writer.close()
        await writer.wait_closed()


async def test_partial_clock_start_failure_does_not_register_peer():
    server = LocalClockServer(0)
    with (
        patch.object(server, "start", AsyncMock(side_effect=OSError)),
        pytest.raises(OSError),
    ):
        await server.register("one", "192.0.2.2")
    assert not server.peers


async def test_reenrollment_reuses_saved_camera_credentials(socket_enabled):
    from dataclasses import replace

    original = LocalEnrollment("127.0.0.1", 0)
    credentials = replace(
        original.credentials,
        rtsp_username="custom",
        rtsp_password="override",
        access_token="custom-access",
    )
    server = LocalEnrollment(
        "127.0.0.1", 0, device=original.device, credentials=credentials
    )
    assert server.account != original.account
    assert server.credentials == credentials
    await server.start()
    connection = await camera(
        server.port, f"dreg synthetic-id {server.account} Test {MODEL}\n".encode()
    )
    try:
        parts = (await connection.readline()).decode().split()
        assert parts[1] == str(credentials.sid_user_id)
        assert parts[-2:] == [
            credentials.magic_token.decode(),
            credentials.sid_device.decode(),
        ]
    finally:
        connection.close()
        await connection.writer.wait_closed()
        await server.stop()


def test_reenrollment_rejects_mismatched_saved_credentials():
    from dataclasses import replace

    original = LocalEnrollment("192.168.12.2")
    with pytest.raises(ValueError):
        LocalEnrollment(
            "192.168.12.2",
            device=original.device,
            credentials=replace(original.credentials, sid_user_id=1),
        )
