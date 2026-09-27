"""Real-time camera event parsing and transport behavior."""

import asyncio
import ssl
from unittest.mock import AsyncMock, Mock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.motorola_nursery.const import DOMAIN
from custom_components.motorola_nursery.events import (
    CameraEventListener,
    parse_notification,
)


def test_notification_parser_filters_camera_and_event_type():
    token = "synthetic-token"
    assert (
        parse_notification(
            ["notify", token, "motiondetect", "motion-20260927.mp4"], token
        )
        == "motion"
    )
    assert (
        parse_notification(
            ["notify", token, "sounddetect2", "sound-20260927.snd"], token
        )
        == "sound"
    )
    for parts in (
        ["notify", "other-token", "motiondetect", "event.mp4"],
        ["notify", token, "snapshot", "private.jpg"],
        ["notify", token, "motiondetect"],
        ["get", token, "motiondetect", "event.mp4"],
    ):
        assert parse_notification(parts, token) is None


@pytest.mark.usefixtures("socket_enabled")
async def test_listener_authenticates_handles_keepalive_and_deduplicates():
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="synthetic-device",
        data={
            "sid_user_id": "123456",
            "sid_device": "synthetic-device",
            "magic_token": "synthetic-token",
            "rtsp_username": "user",
            "rtsp_password": "password",
            "access_token": "access",
            "cloud_session": {"host": "9.moto.5gencare.com"},
        },
    )
    reader = asyncio.StreamReader()
    writer = Mock(drain=AsyncMock(), wait_closed=AsyncMock())
    commands = []

    def write(data):
        commands.append(data)
        if data.startswith(b"app "):
            reader.feed_data(
                b"app 1 OK\nping\n"
                b"notify other-token motiondetect ignored.mp4\n"
                b"notify synthetic-token motiondetect event-1.mp4\n"
                b"notify synthetic-token motiondetect event-1.mp4\n"
                b"notify synthetic-token sounddetect2 event-2.snd\n"
            )
            reader.feed_eof()

    writer.write.side_effect = write
    events = []
    connections = []
    listener = CameraEventListener(
        entry, ssl.create_default_context(), events.append, connections.append
    )
    with (
        patch(
            "asyncio.open_connection", AsyncMock(return_value=(reader, writer))
        ) as open_,
        pytest.raises(OSError),
    ):
        await listener._listen_once()

    assert [event.event_type for event in events] == ["motion", "sound"]
    assert connections == [True, False]
    assert commands[0] == b"app 123456 synthetic-token\n"
    assert b"pong\n" in commands
    assert open_.call_args.kwargs["ssl"] is not None
    assert open_.call_args.kwargs["server_hostname"] == "9.moto.5gencare.com"
    writer.close.assert_called_once()
