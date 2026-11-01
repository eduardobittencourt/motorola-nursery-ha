"""Home Assistant control entities backed by confirmed camera commands."""

from contextlib import asynccontextmanager
from dataclasses import replace
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.config_entries import ConfigEntryState
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
        "video_brightness": Capability("int", 0, 4, True),
        "speaker_volume": Capability("int", 1, 6, True),
        "night_vision": Capability("int", 0, 2, True),
        "video_bitrate": Capability("int", 0, 3, True),
        "videoKbps": Capability("int", 160, 2000, True),
        "lowtemp_switch": Capability("int", 0, 1, True),
        "playing": Capability("str", 1, 128, True),
        "audio_control": Capability("int", 0, 1, True),
        "existsongs": Capability("str", 1, 1024),
        "pan": Capability("str", 1, 16, True),
    },
    values={
        "video_brightness": 1,
        "speaker_volume": 6,
        "night_vision": 2,
        "video_bitrate": 2,
        "videoKbps": 640,
        "lowtemp_switch": 1,
        "playing": "(none)",
        "audio_control": 0,
    },
)


@asynccontextmanager
async def setup_controls(
    hass, data=DATA, model="VM65CONNECT", registered_keys=(), playlist=None
):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Nursery controls",
        unique_id="synthetic-controls",
        data={
            "host": "192.0.2.10",
            "model": model,
            "sid_user_id": "123456",
            "sid_device": "synthetic-controls",
            "magic_token": "synthetic-token",
            "rtsp_username": "user",
            "rtsp_password": "password",
            "access_token": "access",
            "cloud_session": {"host": "9.moto.5gencare.com"},
        },
    )
    entry.add_to_hass(hass)
    for domain, key in registered_keys:
        er.async_get(hass).async_get_or_create(
            domain, DOMAIN, f"{entry.unique_id}:{key}", config_entry=entry
        )
    bridge = Mock(start=AsyncMock(), stop=AsyncMock(), port=12345)
    relay = Mock(start=AsyncMock(), stop=AsyncMock(), url="http://127.0.0.1:12346/test")
    client = Mock(
        async_read=AsyncMock(return_value=data),
        async_set=AsyncMock(side_effect=lambda credentials, key, value: value),
        async_list_songs=AsyncMock(
            return_value=("Twinkle_Little_Star.mp3", "White_Noise.mp3")
        ),
        async_play=AsyncMock(),
        async_stop=AsyncMock(),
        async_ptz=AsyncMock(),
    )
    if playlist is not None:
        client.async_list_songs.side_effect = playlist
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
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done(wait_background_tasks=True)

        try:
            yield entry, client, bridge, relay
        finally:
            if entry.state is ConfigEntryState.LOADED:
                assert await hass.config_entries.async_unload(entry.entry_id)


async def test_control_entities_write_update_and_keep_video_running(hass):
    async with setup_controls(hass) as (entry, client, bridge, relay):
        registry = er.async_get(hass)

        def entity_id(platform, key):
            result = registry.async_get_entity_id(
                platform, DOMAIN, f"{entry.unique_id}:{key}"
            )
            assert result is not None
            return result

        camera_id = registry.async_get_entity_id("camera", DOMAIN, entry.unique_id)
        assert camera_id is not None
        brightness = entity_id("number", "video_brightness")
        night_vision = entity_id("select", "night_vision")
        low_alert = entity_id("switch", "lowtemp_switch")
        pan_left = entity_id("button", "ptz_pan_left")
        lullabies = entity_id("media_player", "lullabies")

        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": brightness, "value": 2},
            blocking=True,
        )
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": night_vision, "option": "off"},
            blocking=True,
        )
        await hass.services.async_call(
            "switch", "turn_off", {"entity_id": low_alert}, blocking=True
        )
        await hass.services.async_call(
            "button", "press", {"entity_id": pan_left}, blocking=True
        )
        await hass.services.async_call(
            "media_player",
            "select_source",
            {"entity_id": lullabies, "source": "White Noise"},
            blocking=True,
        )
        await hass.services.async_call(
            "media_player",
            "volume_set",
            {"entity_id": lullabies, "volume_level": 0.2},
            blocking=True,
        )

        assert hass.states.get(brightness).state == "2"
        assert hass.states.get(night_vision).state == "off"
        assert hass.states.get(low_alert).state == "off"
        assert hass.states.get(lullabies).state == "playing"
        assert hass.states.get(camera_id).state != "unavailable"
        assert ("video_brightness", 2) in [
            (call.args[1], call.args[2]) for call in client.async_set.await_args_list
        ]
        assert ("night_vision", 0) in [
            (call.args[1], call.args[2]) for call in client.async_set.await_args_list
        ]
        assert ("lowtemp_switch", 0) in [
            (call.args[1], call.args[2]) for call in client.async_set.await_args_list
        ]
        assert ("speaker_volume", 2) in [
            (call.args[1], call.args[2]) for call in client.async_set.await_args_list
        ]
        assert client.async_play.await_args.args[1] == "White_Noise.mp3"
        assert client.async_ptz.await_args.args[1:] == ("pan", "left")

        await hass.services.async_call(
            "media_player", "media_stop", {"entity_id": lullabies}, blocking=True
        )
        assert hass.states.get(lullabies).state == "idle"
        client.async_stop.assert_awaited_once()

        assert await hass.config_entries.async_unload(entry.entry_id)


def find_entity(hass, entry, domain, key):
    return er.async_get(hass).async_get_entity_id(
        domain, DOMAIN, f"{entry.unique_id}:{key}"
    )


async def test_vm65_without_ptz_retires_only_unsupported_owned_controls(hass):
    data = replace(
        DATA, capabilities={k: v for k, v in DATA.capabilities.items() if k != "pan"}
    )
    async with setup_controls(
        hass,
        data,
        registered_keys=(
            ("button", "ptz_pan_left"),
            ("button", "ptz_origin"),
            ("button", "unrelated_button"),
        ),
    ) as (entry, client, _, _):
        assert find_entity(hass, entry, "button", "ptz_pan_left") is None
        assert find_entity(hass, entry, "button", "ptz_origin") is None
        assert find_entity(hass, entry, "button", "unrelated_button") is not None
        client.async_ptz.assert_not_awaited()


async def test_dynamic_bounds_read_only_fields_and_per_axis_ptz(hass):
    data = TelemetryData(
        capabilities={
            "video_brightness": Capability("int", 0, 4),
            "motion": Capability("int", 2, 7, True),
            "night_vision": Capability("int", 1, 2, True),
            "video_bitrate": Capability("int", 0, 3),
            "videoKbps": Capability("int", 160, 2000),
            "pan": Capability("str", 1, 16, True),
        },
        values={
            "video_brightness": 1,
            "motion": 3,
            "night_vision": 2,
            "video_bitrate": 2,
            "videoKbps": 640,
        },
    )
    async with setup_controls(hass, data, model="OTHER-MODEL") as (entry, client, _, _):
        assert find_entity(hass, entry, "number", "video_brightness") is None
        motion = find_entity(hass, entry, "number", "motion")
        attrs = hass.states.get(motion).attributes
        assert (attrs["min"], attrs["max"]) == (2, 7)
        night = find_entity(hass, entry, "select", "night_vision")
        assert hass.states.get(night).attributes["options"] == ["on", "auto"]
        assert find_entity(hass, entry, "select", "video_bitrate") is None
        assert find_entity(hass, entry, "sensor", "videoKbps") is not None
        assert find_entity(hass, entry, "button", "ptz_pan_left") is not None
        assert find_entity(hass, entry, "button", "ptz_pan_right") is not None
        assert find_entity(hass, entry, "button", "ptz_tilt_up") is None
        assert find_entity(hass, entry, "button", "ptz_origin") is None
        assert find_entity(hass, entry, "media_player", "lullabies") is None
        client.async_list_songs.assert_not_awaited()

        # An authoritative capability change disables existing controls, retaining IDs.
        caps = dict(data.capabilities)
        caps["motion"] = replace(caps["motion"], writable=False)
        caps["pan"] = replace(caps["pan"], writable=False)
        client.async_read.return_value = replace(data, capabilities=caps)
        await entry.runtime_data.telemetry.async_refresh()
        await hass.async_block_till_done(wait_background_tasks=True)
        assert hass.states.get(motion).state == "unavailable"
        left = find_entity(hass, entry, "button", "ptz_pan_left")
        assert hass.states.get(left).state == "unavailable"
        assert find_entity(hass, entry, "number", "motion") == motion


async def test_playlist_retry_with_unchanged_readings_and_setting_updates(hass):
    async with setup_controls(
        hass,
        playlist=[
            TelemetryError("unavailable"),
            ("White_Noise.mp3",),
            ("White_Noise.mp3",),
        ],
    ) as (entry, client, _, _):
        assert find_entity(hass, entry, "media_player", "lullabies") is None
        assert entry.runtime_data.telemetry.last_update_success
        await entry.runtime_data.telemetry.async_refresh()
        await hass.async_block_till_done(wait_background_tasks=True)
        player = find_entity(hass, entry, "media_player", "lullabies")
        assert hass.states.get(player).attributes["source_list"] == ["White Noise"]
        await entry.runtime_data.telemetry.async_set_value("video_brightness", 2)
        assert hass.states.get(player).attributes["source_list"] == ["White Noise"]
        await entry.runtime_data.telemetry.async_refresh()
        await hass.async_block_till_done(wait_background_tasks=True)
        assert find_entity(hass, entry, "media_player", "lullabies") == player
        assert len(hass.states.async_entity_ids("media_player")) == 1


async def test_media_features_follow_access_and_volume_bounds(hass):
    from homeassistant.components.media_player import MediaPlayerEntityFeature

    caps = dict(DATA.capabilities)
    caps["playing"] = replace(caps["playing"], writable=False)
    caps["audio_control"] = replace(caps["audio_control"], writable=False)
    caps["speaker_volume"] = Capability("int", 0, 10, True)
    data = replace(DATA, capabilities=caps, values={**DATA.values, "speaker_volume": 5})
    async with setup_controls(hass, data) as (entry, client, _, _):
        player = find_entity(hass, entry, "media_player", "lullabies")
        state = hass.states.get(player)
        assert "source_list" not in state.attributes
        assert (
            state.attributes["supported_features"]
            == MediaPlayerEntityFeature.VOLUME_SET
        )
        assert state.attributes["volume_level"] == 0.5
        await hass.services.async_call(
            "media_player",
            "volume_set",
            {"entity_id": player, "volume_level": 0.2},
            blocking=True,
        )
        assert client.async_set.await_args.args[1:] == ("speaker_volume", 2)


async def test_late_playlist_result_does_not_clear_telemetry_failure(hass):
    import asyncio

    from homeassistant.helpers.update_coordinator import UpdateFailed

    async with setup_controls(hass) as (entry, client, _, _):
        coordinator = entry.runtime_data.telemetry
        started, release = asyncio.Event(), asyncio.Event()

        async def delayed_songs(_):
            started.set()
            await release.wait()
            return ("Other_Song.mp3",)

        client.async_list_songs.side_effect = delayed_songs
        await coordinator.async_refresh()
        await started.wait()
        coordinator.async_set_update_error(UpdateFailed("disconnected"))
        release.set()
        await coordinator._playlist_task
        assert coordinator.last_update_success is False
        assert coordinator.data.songs == ("Twinkle_Little_Star.mp3", "White_Noise.mp3")


async def test_playlist_options_respect_advertised_filename_bounds(hass):
    caps = {**DATA.capabilities, "playing": Capability("str", 1, 12, True)}
    data = replace(DATA, capabilities=caps)
    async with setup_controls(
        hass, data, playlist=[("Song.mp3", "Name_Too_Long.mp3")]
    ) as (entry, _, _, _):
        player = find_entity(hass, entry, "media_player", "lullabies")
        assert hass.states.get(player).attributes["source_list"] == ["Song"]
