"""Sensors: COP, temperatures, water pressure and energy counters."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfEnergy, UnitOfPressure, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import RemehaConfigEntry
from .const import CONF_SERIAL, DOMAIN
from .coordinator import RemehaCoordinator


def _temp(key: str) -> SensorEntityDescription:
    return SensorEntityDescription(
        key=key, translation_key=key,
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
    )


def _energy(key: str) -> SensorEntityDescription:
    return SensorEntityDescription(
        key=key, translation_key=key,
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=1,
    )


SENSORS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="cop", translation_key="cop",
        state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=2,
    ),
    SensorEntityDescription(
        key="spf", translation_key="spf",
        state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=1,
    ),
    _temp("outdoor_temperature"),
    _temp("flow_temperature"),
    _temp("heat_pump_flow_temperature"),
    _temp("return_temperature"),
    _temp("flow_setpoint"),
    _temp("dhw_temperature"),
    _temp("dhw_setpoint"),
    SensorEntityDescription(
        key="water_pressure", translation_key="water_pressure",
        device_class=SensorDeviceClass.PRESSURE,
        native_unit_of_measurement=UnitOfPressure.BAR,
        state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=2,
    ),
    _energy("energy_consumed_total"),
    _energy("energy_consumed_heating"),
    _energy("energy_consumed_dhw"),
    _energy("energy_delivered_total"),
    _energy("energy_delivered_heating"),
    _energy("energy_delivered_dhw"),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RemehaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(RemehaSensor(coordinator, d) for d in SENSORS)


class RemehaSensor(CoordinatorEntity[RemehaCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: RemehaCoordinator, desc: SensorEntityDescription) -> None:
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
    def native_value(self) -> float | None:
        return self.coordinator.data.values.get(self.entity_description.key)
