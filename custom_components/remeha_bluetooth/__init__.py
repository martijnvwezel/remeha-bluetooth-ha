"""Remeha heat pump via the EHC-16 Bluetooth module."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant

from .coordinator import RemehaCoordinator
from .pairing import async_remove_bond

PLATFORMS = [Platform.SENSOR]

type RemehaConfigEntry = ConfigEntry[RemehaCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: RemehaConfigEntry) -> bool:
    coordinator = RemehaCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


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
