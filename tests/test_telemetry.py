"""Synthetic control service: bounded reads, framing, TLS and no setters."""

import asyncio
import ssl
from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.motorola_nursery.protocol import Credentials
from custom_components.motorola_nursery.telemetry import (
    Capability,
    TelemetryClient,
    TelemetryError,
    parse_capabilities,
    parse_values,
)

CREDENTIALS = Credentials(
    123456, b"synthetic-device", b"synthetic-token", "user", "pass", "access"
)
CAPS = {
    "temperature_reading": Capability("int", -200, 500),
    "wifi_signal": Capability("int", 0, 100),
}
CAP_LINE = (
    b"caplist 3 temperature_reading r int -200 500 wifi_signal r int 0 100 "
    b"wifi_ssid r str 1 64\n"
)


def test_capabilities_filter_personal_data_and_validate_frames():
    assert parse_capabilities(CAP_LINE.decode().split()) == CAPS
    for message in (
        "caplist -1",
        "caplist 1",
        "caplist 257",
        "caplist 1 wifi_signal r int 100 0",
        "caplist 2 wifi_signal r int 0 100 wifi_signal r int 0 100",
        "caplist 1 wifi_signal r str 0 100",
    ):
        with pytest.raises(TelemetryError, match="Invalid capability"):
            parse_capabilities(message.split())


@pytest.mark.parametrize("value", ["501", "-201", "nan", "secret-value"])
def test_invalid_sensor_value_does_not_hide_other_sensors(value):
    result = parse_values(
        f"get 2 temperature_reading {value} wifi_signal 94".split(), CAPS
    )
    assert result == {"temperature_reading": None, "wifi_signal": 94}


@pytest.mark.parametrize(
    "message",
    [
        "get 1 wifi_signal 94",
        "get 2 temperature_reading 241 wifi_signal",
        "get 2 wifi_signal 94 wifi_signal 90",
        "get 2 temperature_reading 241 wifi_ssid private-network",
        "get -1",
    ],
)
def test_partial_or_unexpected_response_is_rejected(message):
    with pytest.raises(TelemetryError, match="Invalid sensor response") as error:
        parse_values(message.split(), CAPS)
    assert "private-network" not in str(error.value)


def make_transport(
    *, auth=b"app 1 OK\n", values=b"get 2 temperature_reading 241 wifi_signal 94\n"
):
    reader = asyncio.StreamReader()
    writer = Mock()
    writer.drain = AsyncMock()
    writer.wait_closed = AsyncMock()
    commands = []

    def write(data):
        commands.append(data)
        if data.startswith(b"app "):
            response = b"ping\n" + auth
        elif data == b"caplist\n":
            response = CAP_LINE
        elif data.startswith(b"get "):
            response = values
        else:
            assert data in {b"pong\n", b"pang\n"}
            return
        # Exercise TCP fragmentation and multiple complete lines in one read.
        loop = asyncio.get_running_loop()
        for index in range(0, len(response), 3):
            loop.call_soon(reader.feed_data, response[index : index + 3])

    writer.write.side_effect = write
    return reader, writer, commands


async def test_read_uses_verified_tls_and_only_allowed_getters():
    context = ssl.create_default_context()
    client = TelemetryClient("9.moto.5gencare.com", context)
    first, second = make_transport(), make_transport()
    with patch(
        "asyncio.open_connection", AsyncMock(side_effect=[first[:2], second[:2]])
    ) as connect:
        for _ in range(2):
            data = await client.async_read(CREDENTIALS)
            assert data.values == {"temperature_reading": 241, "wifi_signal": 94}
    assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
    assert connect.call_args.kwargs["ssl"] is context
    assert connect.call_args.kwargs["server_hostname"] == "9.moto.5gencare.com"
    assert connect.call_args.args[1] == 2288
    assert b"caplist\n" in first[2] and b"caplist\n" not in second[2]
    for _, writer, commands in (first, second):
        writer.close.assert_called_once()
        writer.wait_closed.assert_awaited_once()
        assert b"get 2 temperature_reading wifi_signal\n" in commands
        assert all(
            line.split()[0] in {b"app", b"caplist", b"get", b"pong"}
            for line in commands
        )


async def test_auth_rejection_does_not_query_or_disclose_credentials():
    reader, writer, commands = make_transport(auth=b"app -1 secret-value\n")
    client = TelemetryClient("9.moto.5gencare.com", ssl.create_default_context())
    with (
        patch("asyncio.open_connection", AsyncMock(return_value=(reader, writer))),
        pytest.raises(TelemetryError, match="authentication") as error,
    ):
        await client.async_read(CREDENTIALS)
    assert "secret-value" not in str(error.value)
    assert "synthetic-token" not in str(error.value)
    assert all(line.split()[0] in {b"app", b"pong"} for line in commands)
    writer.close.assert_called_once()


async def test_timeout_and_cancellation_close_connection():
    client = TelemetryClient("9.moto.5gencare.com", ssl.create_default_context())
    for cancel in (False, True):
        reader = asyncio.StreamReader()
        writer = Mock(drain=AsyncMock(), wait_closed=AsyncMock())
        with (
            patch("asyncio.open_connection", AsyncMock(return_value=(reader, writer))),
            patch(
                "custom_components.motorola_nursery.telemetry.TIMEOUT",
                0.02 if not cancel else 10,
            ),
        ):
            task = asyncio.create_task(client.async_read(CREDENTIALS))
            await asyncio.sleep(0)
            if cancel:
                task.cancel()
            with pytest.raises(asyncio.CancelledError if cancel else TelemetryError):
                await task
        writer.close.assert_called_once()


def test_no_arbitrary_control_host():
    with pytest.raises(Exception, match="Unexpected authentication server"):
        TelemetryClient("example.com", ssl.create_default_context())
