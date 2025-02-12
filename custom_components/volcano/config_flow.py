"""Config flow for Volcano TTS integration."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DOMAIN,
    CONF_APPID,
    CONF_ACCESS_TOKEN,
    CONF_HOST,
    CONF_TTS_CLUSTER,
    CONF_STT_CLUSTER,
    CONF_VOICE_TYPE,
    DEFAULT_HOST,
    DEFAULT_VOICE_TYPE,
    DEFAULT_TTS_CLUSTER,
    DEFAULT_STT_CLUSTER,
)

CONFIG_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): str,
        vol.Required(CONF_APPID): str,
        vol.Required(CONF_ACCESS_TOKEN): str,
        vol.Optional(CONF_TTS_CLUSTER, default=DEFAULT_TTS_CLUSTER): str,
        vol.Optional(CONF_STT_CLUSTER, default=DEFAULT_STT_CLUSTER): str,
        vol.Optional(CONF_HOST, default=DEFAULT_HOST): str,
        vol.Optional(CONF_VOICE_TYPE, default=DEFAULT_VOICE_TYPE): str,
    }
)

async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    # TODO: Add validation logic here if needed
    return {"title": data[CONF_NAME]}

class VolcanoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Volcano TTS."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
                return self.async_create_entry(title=info["title"], data=user_input)
            except Exception:  # pylint: disable=broad-except
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=CONFIG_SCHEMA,
            errors=errors,
        )
