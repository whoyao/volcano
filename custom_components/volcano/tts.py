"""Support for Volcano TTS services."""
from __future__ import annotations

import base64
import json
import logging
import uuid
from typing import Any

import requests
from homeassistant.components import tts
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.core import callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    API_ENDPOINT,
    CONF_ACCESS_TOKEN,
    CONF_APPID,
    CONF_TTS_CLUSTER,
    CONF_VOICE_TYPE,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Volcano TTS entry."""
    async_add_entities(
        [
            VolcanoTtsProvider(hass, config_entry),
        ]
    )


class VolcanoTtsProvider(tts.TextToSpeechEntity):
    """The Volcano TTS API provider."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize Volcano TTS provider."""
        self._attr_name = config_entry.data[CONF_NAME]
        self.hass = hass
        self.config_entry = config_entry
        self._attr_unique_id = f"{config_entry.entry_id}-tts"

    @property
    def default_language(self) -> str:
        """Return the default language."""
        return "zh-cn"

    @property
    def supported_languages(self) -> list[str]:
        """Return list of supported languages."""
        return ["zh-cn", "zh-hk", "zh-tw", "en"]

    @property
    def supported_options(self) -> list[str]:
        """Return list of supported options like voice, emotions."""
        return []

    @property
    def default_options(self) -> dict[str, Any]:
        """Return a dict include default options."""
        return {}

    @callback
    def async_get_supported_voices(self, language: str) -> list[tts.Voice] | None:
        """Return a list of supported voices for a language."""
        return None

    async def async_get_tts_audio(self, message: str, language: str, options: dict[str, Any]) -> tts.TtsAudioType:
        """Load TTS from Volcano."""
        request_data = {
            "app": {
                "appid": self.config_entry.data[CONF_APPID],
                "token": self.config_entry.data[CONF_ACCESS_TOKEN],
                "cluster": self.config_entry.data[CONF_TTS_CLUSTER],
            },
            "user": {
                "uid": str(uuid.uuid4()),
            },
            "audio": {
                "voice_type": self.config_entry.data[CONF_VOICE_TYPE],
                "encoding": "mp3",
                "speed_ratio": 1.0,
                "volume_ratio": 1.0,
                "pitch_ratio": 1.0,
            },
            "request": {
                "reqid": str(uuid.uuid4()),
                "text": message,
                "text_type": "plain",
                "operation": "query",
                "with_frontend": 1,
                "frontend_type": "unitTson"
            }
        }

        headers = {"Authorization": f"Bearer;{self.config_entry.data[CONF_ACCESS_TOKEN]}"}

        try:
            response = requests.post(
                API_ENDPOINT,
                data=json.dumps(request_data),
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()

            if "data" not in data:
                _LOGGER.error("Error getting TTS: %s", data)
                return None, None

            audio_data = base64.b64decode(data["data"])
            return "mp3", audio_data

        except Exception as err:
            _LOGGER.error("Error getting TTS: %s", err)
            return None, None