"""Real HA entity lifecycle, delayed discovery and independent video playback."""

from unittest.mock import AsyncMock, Mock, patch

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.motorola_nursery.const import DOMAIN
from custom_components.motorola_nursery.telemetry import (
    Capability,
    TelemetryData,
    TelemetryError,
)

DATA = TelemetryData(
    capabilities={
        "temperature_reading": Capability("int", -200, 500),
        "wifi_signal": Capability("int", 0, 100),
        "night_vision": Capability("int", 0, 2),
        "lowtemp_switch": Capability("int", 0, 1),
        "firmware_version": Capability("str", 7, 7),
    },
    values={
        "temperature_reading": 241,
        "wifi_signal": 94,
        "night_vision": 2,
        "lowtemp_switch": 1,
        "firmware_version": "V1.6.37",
    },
)


async def test_sensor_discovery_outage_recovery_and_unload(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Nursery test",
        unique_id="synthetic-device",
        data={
            "host": "192.0.2.10",
            "model": "VM65CONNECT",
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
    bridge = Mock(start=AsyncMock(), stop=AsyncMock(), port=12345)
    relay = Mock(start=AsyncMock(), stop=AsyncMock(), url="http://127.0.0.1:12346/test")
    client = Mock(async_read=AsyncMock(side_effect=TelemetryError("Cloud unavailable")))
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
            "custom_components.motorola_nursery.get_ffmpeg_manager",
            return_value=Mock(binary="ffmpeg"),
        ),
        patch(
            "custom_components.motorola_nursery.async_refresh_credentials", AsyncMock()
        ) as refresh,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        registry = er.async_get(hass)
        camera_id = registry.async_get_entity_id("camera", DOMAIN, entry.unique_id)
        assert camera_id is not None
        assert hass.states.get(camera_id).state != "unavailable"
        assert not hass.states.async_entity_ids("sensor")

        client.async_read.side_effect = None
        client.async_read.return_value = DATA
        coordinator = entry.runtime_data.telemetry
        await coordinator.async_refresh()
        await hass.async_block_till_done()

        def entity_id(platform, key):
            return registry.async_get_entity_id(
                platform, DOMAIN, f"{entry.unique_id}:{key}"
            )

        temperature_id = entity_id("sensor", "temperature_reading")
        assert hass.states.get(temperature_id).state == "24.1"
        assert hass.states.get(temperature_id).attributes["unit_of_measurement"] == "°C"
        assert hass.states.get(entity_id("sensor", "night_vision")).state == "auto"
        assert (
            hass.states.get(entity_id("binary_sensor", "lowtemp_switch")).state == "on"
        )
        assert len(hass.states.async_entity_ids("sensor")) == 3
        device_id = registry.async_get(camera_id).device_id
        assert registry.async_get(temperature_id).device_id == device_id
        assert dr.async_get(hass).async_get(device_id).sw_version == "V1.6.37"

        client.async_read.side_effect = TelemetryError("Cloud unavailable")
        await coordinator.async_refresh()
        assert hass.states.get(temperature_id).state == "unavailable"
        assert hass.states.get(camera_id).state != "unavailable"
        relay.stop.assert_not_called()
        bridge.stop.assert_not_called()
        refresh.assert_not_called()

        client.async_read.side_effect = None
        await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert hass.states.get(temperature_id).state == "24.1"
        assert len(hass.states.async_entity_ids("sensor")) == 3

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert not coordinator._listeners
        assert coordinator._unsub_refresh is None
        relay.stop.assert_awaited_once()
        bridge.stop.assert_awaited_once()
