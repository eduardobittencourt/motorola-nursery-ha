"""Slow cloud requests must not block local camera setup or unload."""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.motorola_nursery.const import DOMAIN
from custom_components.motorola_nursery.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.motorola_nursery.telemetry import Capability, TelemetryData


@pytest.mark.parametrize("blocked_stage", ["telemetry", "playlist"])
@pytest.mark.parametrize("finish", ["recover", "unload"])
async def test_slow_cloud_does_not_block_video_and_is_cancelled_on_unload(
    hass, blocked_stage, finish
):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="synthetic-device",
        data={
            "host": "192.0.2.10",
            "sid_user_id": "123456",
            "sid_device": "synthetic-device",
            "magic_token": "synthetic-token",
            "rtsp_username": "user",
            "rtsp_password": "password",
            "access_token": "access",
            "cloud_session": {"host": "9.moto.5gencare.com"},
        },
    )
    entry.add_to_hass(hass)
    started, release, cancelled = asyncio.Event(), asyncio.Event(), asyncio.Event()
    data = TelemetryData(
        {"temperature_reading": Capability("int", -200, 500)},
        {"temperature_reading": 241},
    )

    async def block(stage, result):
        if stage == blocked_stage:
            started.set()
            try:
                await release.wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise
        return result

    async def read(_):
        return await block("telemetry", data)

    async def songs(_):
        return await block("playlist", ("Song.mp3",))

    client = Mock(
        async_read=AsyncMock(side_effect=read),
        async_list_songs=AsyncMock(side_effect=songs),
    )
    bridge = Mock(start=AsyncMock(), stop=AsyncMock(), port=12345, active_connections=0)
    relay = Mock(
        start=AsyncMock(),
        stop=AsyncMock(),
        url="http://127.0.0.1:12346/test",
        active_processes=0,
    )
    events = Mock(start=Mock(), stop=AsyncMock(), connected=False, latest={})
    with (
        patch(
            "homeassistant.components.ffmpeg.async_setup", AsyncMock(return_value=True)
        ),
        patch(
            "homeassistant.components.stream.async_setup", AsyncMock(return_value=True)
        ),
        patch("custom_components.motorola_nursery.RtspBridge", return_value=bridge),
        patch("custom_components.motorola_nursery.FfmpegRelay", return_value=relay),
        patch(
            "custom_components.motorola_nursery.TelemetryClient", return_value=client
        ),
        patch(
            "custom_components.motorola_nursery.MotorolaEventManager",
            return_value=events,
        ),
        patch(
            "custom_components.motorola_nursery.get_ffmpeg_manager",
            return_value=Mock(binary="ffmpeg"),
        ),
        patch(
            "custom_components.motorola_nursery.MagicP2PTunnel.connect",
            AsyncMock(return_value=AsyncMock()),
        ),
    ):
        assert await asyncio.wait_for(
            hass.config_entries.async_setup(entry.entry_id), 2
        )
        await asyncio.wait_for(started.wait(), 1)
        await hass.async_block_till_done()
        registry = er.async_get(hass)
        camera_id = registry.async_get_entity_id("camera", DOMAIN, entry.unique_id)
        assert hass.states.get(camera_id).state != "unavailable"
        camera = hass.data["camera"].get_entity(camera_id)
        assert await camera.stream_source() == relay.url
        events.start.assert_called_once()
        diagnostics = await async_get_config_entry_diagnostics(hass, entry)
        assert diagnostics["initial_telemetry_pending"] == (
            blocked_stage == "telemetry"
        )

        if finish == "recover":
            release.set()
            await entry.runtime_data.telemetry_task
            await hass.async_block_till_done(wait_background_tasks=True)
            sensor_id = registry.async_get_entity_id(
                "sensor", DOMAIN, f"{entry.unique_id}:temperature_reading"
            )
            assert hass.states.get(sensor_id).state == "24.1"
            player_id = registry.async_get_entity_id(
                "media_player", DOMAIN, f"{entry.unique_id}:lullabies"
            )
            assert hass.states.get(player_id).attributes["source_list"] == ["Song"]
        assert await asyncio.wait_for(
            hass.config_entries.async_unload(entry.entry_id), 2
        )
        await hass.async_block_till_done()
        assert cancelled.is_set() == (finish == "unload")
        bridge.stop.assert_awaited_once()
        relay.stop.assert_awaited_once()
