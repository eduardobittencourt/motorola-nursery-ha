"""Real HA entity lifecycle, delayed discovery and independent video playback."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
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
        "night_vision": Capability("int", 0, 2, True),
        "lowtemp_switch": Capability("int", 0, 1, True),
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


@pytest.mark.parametrize("bitrate_control", [False, True])
async def test_sensor_discovery_outage_recovery_and_unload(hass, bitrate_control):
    data = TelemetryData(
        capabilities={**DATA.capabilities, "videoKbps": Capability("int", 160, 1000)},
        values={**DATA.values, "videoKbps": 640},
    )
    if bitrate_control:
        data.capabilities["video_bitrate"] = Capability("int", 0, 3, True)
        data.values["video_bitrate"] = 2
    sensor_count = 2 if bitrate_control else 3
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
    registry = er.async_get(hass)
    legacy_bitrate = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{entry.unique_id}:videoKbps",
        config_entry=entry,
        suggested_object_id="custom_bitrate",
    )
    bridge = Mock(start=AsyncMock(), stop=AsyncMock(), port=12345)
    relay = Mock(start=AsyncMock(), stop=AsyncMock(), url="http://127.0.0.1:12346/test")
    client = Mock(
        async_read=AsyncMock(side_effect=TelemetryError("Cloud unavailable")),
        async_list_songs=AsyncMock(return_value=()),
    )
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
        assert registry.async_get(legacy_bitrate.entity_id) == legacy_bitrate

        client.async_read.side_effect = None
        client.async_read.return_value = data
        coordinator = entry.runtime_data.telemetry
        await coordinator.async_refresh()
        await hass.async_block_till_done()

        def entity_id(platform, key):
            return registry.async_get_entity_id(
                platform, DOMAIN, f"{entry.unique_id}:{key}"
            )

        bitrate_sensor = entity_id("sensor", "videoKbps")
        bitrate_select = entity_id("select", "video_bitrate")
        if bitrate_control:
            assert bitrate_sensor is None
            assert registry.async_get(legacy_bitrate.entity_id) is None
            assert hass.states.get(bitrate_select).state == "640_kbit_s"
        else:
            assert bitrate_select is None
            assert bitrate_sensor == legacy_bitrate.entity_id
            assert hass.states.get(bitrate_sensor).state == "640"
            assert (
                hass.states.get(bitrate_sensor).attributes["unit_of_measurement"]
                == "kbit/s"
            )
        temperature_id = entity_id("sensor", "temperature_reading")
        assert hass.states.get(temperature_id).state == "24.1"
        assert hass.states.get(temperature_id).attributes["unit_of_measurement"] == "°C"
        assert entity_id("sensor", "night_vision") is None
        assert hass.states.get(entity_id("select", "night_vision")).state == "auto"
        assert hass.states.get(entity_id("switch", "lowtemp_switch")).state == "on"
        assert len(hass.states.async_entity_ids("sensor")) == sensor_count
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
        assert len(hass.states.async_entity_ids("sensor")) == sensor_count

        # A fallback must survive bad replacement values and return after removal.
        if not bitrate_control:
            data = TelemetryData(dict(data.capabilities), dict(data.values))
            data.capabilities["video_bitrate"] = Capability("int", 0, 3, True)
            for invalid in (None, 99):
                data.values["video_bitrate"] = invalid
                client.async_read.return_value = TelemetryData(
                    dict(data.capabilities), dict(data.values)
                )
                await coordinator.async_refresh()
                await hass.async_block_till_done()
                assert entity_id("sensor", "videoKbps") == legacy_bitrate.entity_id
                assert hass.states.get(legacy_bitrate.entity_id).state == "640"

            for replacement in (None, "absent", 99):
                data.capabilities["video_bitrate"] = Capability("int", 0, 3, True)
                data.values["video_bitrate"] = 2
                client.async_read.return_value = TelemetryData(
                    dict(data.capabilities), dict(data.values)
                )
                await coordinator.async_refresh()
                await hass.async_block_till_done()
                assert entity_id("sensor", "videoKbps") is None
                assert hass.states.get(legacy_bitrate.entity_id) is None
                assert (
                    hass.states.get(entity_id("select", "video_bitrate")).state
                    == "640_kbit_s"
                )

                if replacement == "absent":
                    del data.capabilities["video_bitrate"]
                    del data.values["video_bitrate"]
                else:
                    data.values["video_bitrate"] = replacement
                client.async_read.return_value = TelemetryData(
                    dict(data.capabilities), dict(data.values)
                )
                await coordinator.async_refresh()
                await hass.async_block_till_done()
                assert entity_id("sensor", "videoKbps") == legacy_bitrate.entity_id
                assert hass.states.get(legacy_bitrate.entity_id).state == "640"
                assert len(hass.states.async_entity_ids("sensor")) == 3

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert not coordinator._listeners
        assert coordinator._unsub_refresh is None
        relay.stop.assert_awaited_once()
        bridge.stop.assert_awaited_once()


async def test_removes_only_owned_setting_mirrors_and_preserves_controls(hass):
    from custom_components.motorola_nursery.entity import (
        SETTING_MIRRORS,
        async_remove_setting_mirrors,
    )

    entry = MockConfigEntry(domain=DOMAIN, unique_id="migrated-camera")
    other = MockConfigEntry(domain=DOMAIN, unique_id="other-camera")
    entry.add_to_hass(hass)
    other.add_to_hass(hass)
    registry = er.async_get(hass)
    removed, kept = [], []
    for index, ((domain, key), (control_domain, control_key)) in enumerate(
        SETTING_MIRRORS.items()
    ):
        legacy = registry.async_get_or_create(
            domain,
            DOMAIN,
            f"{entry.unique_id}:{key}",
            config_entry=entry,
            suggested_object_id=f"legacy_{index}",
        )
        removed.append(legacy.entity_id)
        hass.states.async_set(legacy.entity_id, "unavailable", {"restored": True})
        kept.append(
            registry.async_get_or_create(
                control_domain,
                DOMAIN,
                f"{entry.unique_id}:{control_key}",
                config_entry=entry,
                suggested_object_id=f"custom_control_{index}",
            )
        )
        kept.append(
            registry.async_get_or_create(
                domain,
                DOMAIN,
                f"{other.unique_id}:{key}",
                config_entry=other,
                suggested_object_id=f"other_legacy_{index}",
            )
        )
    for domain, key in (
        ("sensor", "temperature_reading"),
        ("sensor", "wifi_signal"),
        ("binary_sensor", "motion_detected"),
        ("binary_sensor", "sound_detected"),
        ("sensor", "unrelated_value"),
    ):
        kept.append(
            registry.async_get_or_create(
                domain,
                DOMAIN,
                f"{entry.unique_id}:{key}",
                config_entry=entry,
                suggested_object_id=f"keep_{key}",
            )
        )

    assert len(removed) == 16
    async_remove_setting_mirrors(hass, entry)
    bitrate_id = registry.async_get_entity_id(
        "sensor", DOMAIN, f"{entry.unique_id}:videoKbps"
    )
    assert bitrate_id in removed
    assert all(
        registry.async_get(entity_id) is None
        for entity_id in removed
        if entity_id != bitrate_id
    )
    async_remove_setting_mirrors(hass, entry, remove_bitrate=True)
    await hass.async_block_till_done()
    assert all(registry.async_get(entity_id) is None for entity_id in removed)
    assert all(hass.states.get(entity_id) is None for entity_id in removed)
    assert all(registry.async_get(item.entity_id) == item for item in kept)
    async_remove_setting_mirrors(hass, entry)
    assert all(registry.async_get(item.entity_id) == item for item in kept)
