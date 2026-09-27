"""Home Assistant control entities backed by confirmed camera commands."""

from unittest.mock import AsyncMock, Mock, patch

from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.motorola_nursery.const import DOMAIN
from custom_components.motorola_nursery.telemetry import Capability, TelemetryData

DATA = TelemetryData(
    capabilities={
        "video_brightness": Capability("int", 0, 4),
        "speaker_volume": Capability("int", 1, 6),
        "night_vision": Capability("int", 0, 2),
        "video_bitrate": Capability("int", 0, 3),
        "videoKbps": Capability("int", 160, 2000),
        "lowtemp_switch": Capability("int", 0, 1),
        "playing": Capability("str", 1, 128),
        "audio_control": Capability("int", 0, 1),
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


async def test_control_entities_write_update_and_keep_video_running(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Nursery controls",
        unique_id="synthetic-controls",
        data={
            "host": "192.0.2.10",
            "model": "VM65CONNECT",
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
    bridge = Mock(start=AsyncMock(), stop=AsyncMock(), port=12345)
    relay = Mock(start=AsyncMock(), stop=AsyncMock(), url="http://127.0.0.1:12346/test")
    client = Mock(
        async_read=AsyncMock(return_value=DATA),
        async_set=AsyncMock(side_effect=lambda credentials, key, value: value),
        async_list_songs=AsyncMock(
            return_value=("Twinkle_Little_Star.mp3", "White_Noise.mp3")
        ),
        async_play=AsyncMock(),
        async_stop=AsyncMock(),
        async_ptz=AsyncMock(),
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
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

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
