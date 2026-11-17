"""Polls the heat pump over one long-lived BLE connection."""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from bleak import BleakClient
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import AuthError, RemehaData, RemehaSession
from .const import CONF_PIN, DOMAIN, UPDATE_INTERVAL_S
from .pairing import InvalidPin, PairingError, async_ensure_paired

_LOGGER = logging.getLogger(__name__)


class CannotConnect(Exception):
    """Gateway not reachable."""


async def async_open_session(
    hass: HomeAssistant, address: str, pin: str
) -> tuple[BleakClient, RemehaSession]:
    """Bond (if needed), connect and authenticate. Used by flow and coordinator."""
    ble_device = bluetooth.async_ble_device_from_address(hass, address, connectable=True)
    if ble_device is None:
        raise CannotConnect("Gateway not in range")

    details = ble_device.details if isinstance(ble_device.details, dict) else {}
    await async_ensure_paired(address, pin, details.get("path"))

    client = await establish_connection(
        BleakClientWithServiceCache, ble_device, ble_device.name or address,
        max_attempts=4,
    )
    try:
        session = RemehaSession(client)
        await session.authenticate()
    except BaseException:
        await client.disconnect()
        raise
    return client, session


class RemehaCoordinator(DataUpdateCoordinator[RemehaData]):
    """Keeps the BLE session open and reads all values every interval."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass, _LOGGER, config_entry=entry, name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL_S),
        )
        self.address: str = entry.data[CONF_ADDRESS]
        self._pin: str = entry.data[CONF_PIN]
        self._client: BleakClient | None = None
        self._session: RemehaSession | None = None
        self._lock = asyncio.Lock()

    async def _async_update_data(self) -> RemehaData:
        async with self._lock:
            try:
                if self._client is None or not self._client.is_connected:
                    await self._close()
                    self._client, self._session = await async_open_session(
                        self.hass, self.address, self._pin
                    )
                assert self._session is not None
                return await self._session.read_all()
            except InvalidPin as err:
                await self._close()
                raise UpdateFailed("The gateway refused the PIN") from err
            except (CannotConnect, AuthError, PairingError, Exception) as err:  # noqa: BLE001
                await self._close()
                raise UpdateFailed(f"No connection with the heat pump: {err}") from err

    async def async_read_raw(self, index: int, sub: int, element: int) -> bytes | None:
        """Read one object on the open session (diagnostics)."""
        async with self._lock:
            if self._session is None or self._client is None or not self._client.is_connected:
                await self._close()
                self._client, self._session = await async_open_session(
                    self.hass, self.address, self._pin
                )
            return await self._session.read(index, sub, element)

    async def _close(self) -> None:
        client, self._client, self._session = self._client, None, None
        if client is not None:
            try:
                await client.disconnect()
            except Exception:  # noqa: BLE001
                pass

    async def async_shutdown(self) -> None:
        await super().async_shutdown()
        async with self._lock:
            await self._close()
