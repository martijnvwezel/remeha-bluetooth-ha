"""Sensors: COP, temperatures, water pressure and energy counters."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfEnergy,
    UnitOfPressure,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import RemehaConfigEntry
from .const import CONF_SERIAL, DOMAIN
from .coordinator import RemehaCoordinator
from .status import STATUS, SUBSTATUS


@dataclass(frozen=True, kw_only=True)
class RemehaSensorDescription(SensorEntityDescription):
    """Sensor with an optional function turning raw values into a state."""

    value_fn: Callable[[dict], str | float | None] | None = None


def _status(values: dict) -> str | None:
    code = values.get("status_code")
    return None if code is None else STATUS.get(code, "unknown")


def _substatus(values: dict) -> str | None:
    code = values.get("substatus_code")
    return None if code is None else SUBSTATUS.get(code, f"Code {code}")


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
    RemehaSensorDescription(
        key="status", translation_key="status",
        device_class=SensorDeviceClass.ENUM,
        options=sorted(set(STATUS.values())),
        value_fn=_status,
    ),
    RemehaSensorDescription(
        key="substatus", translation_key="substatus",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_substatus,
    ),
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
    def native_value(self) -> str | float | None:
        values = self.coordinator.data.values
        fn = getattr(self.entity_description, "value_fn", None)
        if fn is not None:
            return fn(values)
        return values.get(self.entity_description.key)
