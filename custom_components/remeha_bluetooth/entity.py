"""Shared base: every entity belongs to the one "Heat pump" device."""

from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_SERIAL, DOMAIN
from .coordinator import RemehaCoordinator


class RemehaEntity(CoordinatorEntity[RemehaCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: RemehaCoordinator, desc: EntityDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = desc
        address = coordinator.address
        self._attr_unique_id = f"{address}_{desc.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, address)},
            connections={(CONNECTION_BLUETOOTH, address)},
            manufacturer="Remeha",
            model="EHC-16 Bluetooth module",
            serial_number=coordinator.config_entry.data.get(CONF_SERIAL),
            translation_key="heat_pump",
        )

    @property
    def _value(self):
        return self.coordinator.data.values.get(self.entity_description.key)
