"""Camera-side lullabies discovered from a successfully loaded playlist."""

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityDescription,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError

from .capabilities import playlist_supported, setting_supported, writable
from .entity import MotorolaCoordinatorEntity, async_remove_unsupported_controls

DESCRIPTION = MediaPlayerEntityDescription(
    key="lullabies", translation_key="lullabies", icon="mdi:music-box"
)


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data.telemetry
    if coordinator is None:
        return
    added = discovered = False

    @callback
    def discover():
        nonlocal added, discovered
        if not coordinator.last_update_success or coordinator.data is None:
            return
        supported = playlist_supported(coordinator.data)
        if not discovered:
            async_remove_unsupported_controls(
                hass,
                entry,
                "media_player",
                {"lullabies"},
                {"lullabies"} if supported else set(),
            )
            discovered = True
        if supported and coordinator.data.songs and not added:
            added = True
            async_add_entities([MotorolaLullabyPlayer(coordinator, entry)])

    entry.async_on_unload(coordinator.async_add_listener(discover))
    discover()


class MotorolaLullabyPlayer(MotorolaCoordinatorEntity, MediaPlayerEntity):
    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, DESCRIPTION.key)
        self.entity_description = DESCRIPTION

    @property
    def _sources(self):
        data = self.coordinator.data
        cap = data.capabilities.get("playing") if data else None
        if cap is None:
            return {}
        songs = data.songs
        # A filename suffix keeps source names distinct if prettified names collide.
        names = {}
        for song in songs or ():
            if not cap.minimum <= len(song) <= cap.maximum:
                continue
            name = song.removesuffix(".mp3").replace("_", " ")
            if name in names:
                name = song
            names[name] = song
        return names

    @property
    def supported_features(self):
        data = self.coordinator.data
        features = MediaPlayerEntityFeature(0)
        if writable(data, "playing", "str") and self._sources:
            features |= MediaPlayerEntityFeature.SELECT_SOURCE
        cap = data.capabilities.get("audio_control") if data else None
        if writable(data, "audio_control") and cap.minimum <= 0 <= cap.maximum:
            features |= MediaPlayerEntityFeature.STOP
        if setting_supported(data, "speaker_volume"):
            features |= MediaPlayerEntityFeature.VOLUME_SET
        return features

    @property
    def available(self) -> bool:
        data = self.coordinator.data
        return bool(
            super().available
            and playlist_supported(data)
            and self._sources
            and data.values.get("playing") is not None
            and data.values.get("audio_control") in (0, 1)
        )

    @property
    def state(self):
        data = self.coordinator.data
        if data and data.values.get("audio_control") == 1:
            return MediaPlayerState.PLAYING
        return MediaPlayerState.IDLE

    @property
    def source_list(self):
        return list(self._sources)

    @property
    def source(self):
        data = self.coordinator.data
        playing = data.values.get("playing") if data else None
        return next(
            (name for name, song in self._sources.items() if song == playing), None
        )

    @property
    def media_title(self):
        return self.source

    @property
    def volume_level(self):
        data = self.coordinator.data
        cap = data.capabilities.get("speaker_volume") if data else None
        value = data.values.get("speaker_volume") if data else None
        if cap and isinstance(value, int) and cap.minimum < cap.maximum:
            return (value - cap.minimum) / (cap.maximum - cap.minimum)
        return None

    async def async_select_source(self, source: str) -> None:
        if not self.supported_features & MediaPlayerEntityFeature.SELECT_SOURCE:
            raise HomeAssistantError("Camera playback is not supported")
        try:
            song = self._sources[source]
        except KeyError:
            raise HomeAssistantError("Unknown camera lullaby") from None
        await self.coordinator.async_play(song)

    async def async_media_stop(self) -> None:
        if not self.supported_features & MediaPlayerEntityFeature.STOP:
            raise HomeAssistantError("Camera playback stop is not supported")
        await self.coordinator.async_stop_playback()

    async def async_set_volume_level(self, volume: float) -> None:
        if not self.supported_features & MediaPlayerEntityFeature.VOLUME_SET:
            raise HomeAssistantError("Camera volume is not supported")
        cap = self.coordinator.data.capabilities["speaker_volume"]
        raw = round(cap.minimum + max(0, min(1, volume)) * (cap.maximum - cap.minimum))
        await self.coordinator.async_set_value("speaker_volume", raw)
