"""Camera-side lullaby playback using its validated built-in playlist."""

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityDescription,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.exceptions import HomeAssistantError

from .entity import MotorolaCoordinatorEntity

DESCRIPTION = MediaPlayerEntityDescription(
    key="lullabies",
    translation_key="lullabies",
    icon="mdi:music-box",
)


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data.telemetry
    if coordinator is None:
        return
    async_add_entities([MotorolaLullabyPlayer(coordinator, entry)])


class MotorolaLullabyPlayer(MotorolaCoordinatorEntity, MediaPlayerEntity):
    _attr_supported_features = (
        MediaPlayerEntityFeature.SELECT_SOURCE
        | MediaPlayerEntityFeature.STOP
        | MediaPlayerEntityFeature.VOLUME_SET
    )

    def __init__(self, coordinator, entry):
        super().__init__(coordinator, entry, DESCRIPTION.key)
        self.entity_description = DESCRIPTION
        self._sources: dict[str, str] = {}
        self._loading_sources = False

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        await self._async_load_sources()

    async def _async_load_sources(self) -> None:
        if self._sources or self._loading_sources:
            return
        self._loading_sources = True
        try:
            songs = await self.coordinator.async_list_songs()
        except HomeAssistantError:
            return
        finally:
            self._loading_sources = False
        self._sources = {
            song.removesuffix(".mp3").replace("_", " "): song for song in songs
        }
        self.async_write_ha_state()

    def _handle_coordinator_update(self) -> None:
        if (
            self.coordinator.last_update_success
            and not self._sources
            and not self._loading_sources
        ):
            self.hass.async_create_task(self._async_load_sources())
        super()._handle_coordinator_update()

    @property
    def available(self) -> bool:
        values = self.coordinator.data.values if self.coordinator.data else {}
        return super().available and all(
            key in values for key in ("playing", "audio_control", "speaker_volume")
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
            (
                display
                for display, filename in self._sources.items()
                if filename == playing
            ),
            None,
        )

    @property
    def media_title(self):
        return self.source

    @property
    def volume_level(self):
        data = self.coordinator.data
        value = data.values.get("speaker_volume") if data else None
        return (value - 1) / 5 if isinstance(value, int) else None

    async def async_select_source(self, source: str) -> None:
        if not self._sources:
            await self._async_load_sources()
        try:
            song = self._sources[source]
        except KeyError:
            raise HomeAssistantError("Unknown camera lullaby") from None
        await self.coordinator.async_play(song)

    async def async_media_stop(self) -> None:
        await self.coordinator.async_stop_playback()

    async def async_set_volume_level(self, volume: float) -> None:
        raw = min(6, max(1, round(volume * 5) + 1))
        await self.coordinator.async_set_value("speaker_volume", raw)
