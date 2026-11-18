"""On/off datapoints (compressor, pump, defrost, ...), chosen in Advanced mode."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import RemehaConfigEntry
from .entity import RemehaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RemehaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        RemehaBinarySensor(
            coordinator,
            BinarySensorEntityDescription(
                key=e.key, translation_key=e.key,
                device_class=BinarySensorDeviceClass(e.device_class) if e.device_class else None,
                entity_category=EntityCategory.DIAGNOSTIC if e.diagnostic else None,
            ),
        )
        for e in coordinator.extras if e.binary
    )


class RemehaBinarySensor(RemehaEntity, BinarySensorEntity):
    @property
    def is_on(self) -> bool | None:
        return self._value
