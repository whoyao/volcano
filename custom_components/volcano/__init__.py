"""The Volcano Audio integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import discovery
from homeassistant.helpers.typing import ConfigType

PLATFORMS = [Platform.TTS, Platform.STT]

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Volcano Audio component."""
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Volcano Audio from a config entry."""
    hass.data.setdefault(entry.entry_id, {})
    
    # Set up each platform separately to avoid blocking imports
    for platform in PLATFORMS:
        hass.async_create_task(
            discovery.async_load_platform(
                hass,
                platform,
                entry.domain,
                {"config": entry},
                entry.data
            )
        )
    
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)