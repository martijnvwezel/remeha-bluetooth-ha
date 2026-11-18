"""Remeha heat pump via the EHC-16 Bluetooth module."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.typing import ConfigType

from .catalog import BY_KEY
from .const import DOMAIN
from .coordinator import RemehaCoordinator
from .pairing import async_remove_bond

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]

type RemehaConfigEntry = ConfigEntry[RemehaCoordinator]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

READ_SCHEMA = vol.Schema(
    {
        vol.Required("index"): vol.Any(cv.positive_int, cv.string),
        vol.Optional("sub", default=0): cv.positive_int,
        vol.Optional("element", default=1): cv.positive_int,
    }
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the diagnostic read_object service."""

    async def read_object(call: ServiceCall) -> ServiceResponse:
        index = call.data["index"]
        index = int(index, 0) if isinstance(index, str) else index
        entries = hass.config_entries.async_loaded_entries(DOMAIN)
        if not entries:
            raise HomeAssistantError("No Remeha Bluetooth device set up")
        data = await entries[0].runtime_data.async_read_raw(
            index, call.data["sub"], call.data["element"]
        )
        if data is None:
            raise HomeAssistantError("No answer from the gateway")
        return {
            "hex": data.hex(),
            "int16": [
                int.from_bytes(data[i:i + 2], "little", signed=True)
                for i in range(0, len(data) - 1, 2)
            ],
        }

    hass.services.async_register(
        DOMAIN, "read_object", read_object, schema=READ_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: RemehaConfigEntry) -> bool:
    coordinator = RemehaCoordinator(hass, entry)
    _remove_unused_entities(hass, entry, {e.key for e in coordinator.extras})
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


def _remove_unused_entities(hass: HomeAssistant, entry: ConfigEntry, active: set[str]) -> None:
    """Drop optional entities the user switched off, so no 'unavailable' leftovers."""
    registry = er.async_get(hass)
    prefix = f"{entry.data[CONF_ADDRESS]}_"
    for ent in er.async_entries_for_config_entry(registry, entry.entry_id):
        key = ent.unique_id.removeprefix(prefix)
        if key in BY_KEY and key not in active:
            registry.async_remove(ent.entity_id)


async def async_unload_entry(hass: HomeAssistant, entry: RemehaConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        await entry.runtime_data.async_shutdown()
    return ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Forget the Bluetooth bond so a new setup starts clean."""
    try:
        await async_remove_bond(entry.data[CONF_ADDRESS])
    except Exception:  # noqa: BLE001
        pass
