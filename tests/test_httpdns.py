"""Synthetic SDK HTTP-DNS peers: isolation, hostile input and cleanup."""

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.motorola_nursery.bootstrap import LocalHttpDnsServer
from tests.test_bootstrap import exchange


def request(host="192.168.12.3.5gencare.com", *, target=None, headers=""):
    target = target or f"/199714/resolve?host={host}&udid=123456"
    return f"GET {target} HTTP/1.1\r\nHost: synthetic\r\n{headers}\r\n".encode()


async def test_httpdns_fixed_local_response_peer_isolation_and_shared_lifecycle(
    socket_enabled,
):
    server = LocalHttpDnsServer(0)
    await server.register("one", "127.0.0.1", "192.168.12.3")
    await server.register("two", "192.0.2.2", "192.168.12.4")
    try:
        for suffix in ("", ".lan"):
            host = "192.168.12.3.5gencare.com" + suffix
            response = await exchange(server.port, request(host))
            head, body = response.split(b"\r\n\r\n")
            assert head.startswith(b"HTTP/1.1 200 OK")
            assert f"Content-Length: {len(body)}".encode() in head
            assert json.loads(body) == {
                "dns": [{"host": host, "ips": ["192.168.12.3"]}]
            }
        assert await exchange(server.port, request("192.168.12.4.5gencare.com")) == b""
        await server.unregister("one")
        assert server.server is not None
        assert await exchange(server.port, request()) == b""
    finally:
        await server.unregister("two")
    assert server.server is None and not server.tasks and not server.peers


@pytest.mark.parametrize(
    "payload",
    [
        request("example.com"),
        request(target="http://example.com/199714/resolve?host=example.com&udid=1"),
        request(target="/199714/resolve?host=example.com&host=example.com"),
        request(target="/199714/resolve?host=example.com&udid=1&extra=1"),
        request(target="/199714/resolve?host=example.com&udid="),
        request(target="/199714/resolve?host=example.com&udid=12345678901234567"),
        request(target="/199714/resolve?host=example.com&udid=abc"),
        request(target="/other?host=example.com&udid=1"),
        request(headers="Content-Length: 1\r\n"),
        request(headers="Transfer-Encoding: chunked\r\n"),
        request(headers="Malformed\r\n"),
        request(headers="X-Huge: " + "x" * 4200 + "\r\n"),
        request().replace(b"GET ", b"POST "),
        request().replace(b"HTTP/1.1", b"HTTP/2"),
        b"GET /\xff HTTP/1.1\r\n\r\n",
    ],
)
async def test_httpdns_rejects_unsupported_requests_without_private_logging(
    socket_enabled, payload, caplog
):
    import logging

    caplog.set_level(
        logging.DEBUG, logger="custom_components.motorola_nursery.bootstrap"
    )
    server = LocalHttpDnsServer(0)
    await server.register("one", "127.0.0.1", "192.168.12.3")
    try:
        assert await exchange(server.port, payload) == b""
        assert "192.168.12.3" not in caplog.text
        assert "123456" not in caplog.text
        assert "example.com" not in caplog.text
    finally:
        await server.unregister("one")


async def test_httpdns_cancels_stalled_clients_and_failed_start_does_not_register(
    socket_enabled,
):
    server = LocalHttpDnsServer(0)
    with (
        patch.object(server, "start", AsyncMock(side_effect=OSError)),
        pytest.raises(OSError),
    ):
        await server.register("one", "127.0.0.1", "192.168.12.3")
    assert not server.peers
    await server.register("one", "127.0.0.1", "192.168.12.3")
    reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
    try:
        writer.write(b"GET /")
        await writer.drain()
        await asyncio.sleep(0)
        await asyncio.wait_for(server.unregister("one"), 1)
        assert await reader.read() == b""
        assert server.server is None and not server.tasks
    finally:
        writer.close()
        await writer.wait_closed()


async def test_httpdns_caps_simultaneous_clients(socket_enabled):
    server = LocalHttpDnsServer(0)
    await server.register("one", "127.0.0.1", "192.168.12.3")
    clients = []
    accepted = asyncio.Event()
    original = server.handle
    count = 0

    async def observe(reader, writer):
        nonlocal count
        count += 1
        if count == 4:
            accepted.set()
        await original(reader, writer)

    server.handle = observe
    try:
        for _ in range(4):
            clients.append(await asyncio.open_connection("127.0.0.1", server.port))
        await asyncio.wait_for(accepted.wait(), 1)
        extra_reader, extra_writer = await asyncio.open_connection(
            "127.0.0.1", server.port
        )
        clients.append((extra_reader, extra_writer))
        assert await asyncio.wait_for(extra_reader.read(), 1) == b""
        assert len(server.tasks) == 4
    finally:
        await server.unregister("one")
        for _, writer in clients:
            writer.close()
            await writer.wait_closed()
    assert not server.tasks
