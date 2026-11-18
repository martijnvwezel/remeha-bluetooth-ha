"""Optional datapoints the user can switch on (Advanced mode).

No Home Assistant imports: also used by tools/try_client.py.
Every object below was checked live on an EHC-16 (Remeha Confida/Elga Ace family).
Sources: the 0x501d monitoring block, the Remeha app parameter codes and
github.com/mcc-tweakers/esphome-remeha-confida.
"""

from __future__ import annotations

from dataclasses import dataclass

from .protocol import uint32

MONITOR_BLOCK = 0x501D


@dataclass(frozen=True)
class Extra:
    key: str
    name: str          # English entity name
    name_nl: str       # Dutch entity name
    code: str          # Remeha parameter code shown in the app ("" if none)
    index: int         # object index (MONITOR_BLOCK = read from the shared block)
    sub: int = 0       # subindex, or byte offset when index == MONITOR_BLOCK
    vtype: str = "i16"  # i16 | u16 | u8 | u32 | bool
    scale: float = 1
    unit: str | None = None
    device_class: str | None = None
    state_class: str | None = "measurement"
    precision: int | None = None
    diagnostic: bool = False
    binary: bool = False
    default: bool = False  # also shown in Simple mode


def _t(key, name, nl, code, index, sub, scale=100, **kw) -> Extra:
    return Extra(key, name, nl, code, index, sub, "i16", scale, "°C", "temperature",
                 precision=1, **kw)


def _count(key, name, nl, code, index, sub=0, scale=1, unit=None, dc=None, **kw) -> Extra:
    return Extra(key, name, nl, code, index, sub, "u32", scale, unit, dc,
                 "total_increasing", precision=0 if scale == 1 else 1, **kw)


def _flag(key, name, nl, code, index, sub=0, dc=None) -> Extra:
    return Extra(key, name, nl, code, index, sub, "bool", device_class=dc,
                 state_class=None, binary=True)


B = MONITOR_BLOCK
EXTRAS: tuple[Extra, ...] = (
    # --- power ---
    Extra("electric_power", "Electrical power", "Elektrisch vermogen", "HM161",
          0x43B5, 0, "u16", 10, "kW", "power", precision=2, default=True),
    Extra("heat_output", "Heat output", "Warmte-afgifte", "HM160",
          0x43B4, 0, "u16", 10, "kW", "power", precision=2, default=True),
    Extra("compressor_frequency", "Compressor frequency", "Compressorfrequentie", "",
          0x4353, 0, "u8", 1, "Hz", "frequency", precision=0),
    Extra("compressor_current", "Compressor current", "Stroom compressor", "HM062",
          0x4340, 0, "u16", 10, "A", "current", precision=1),
    Extra("odu_modulation", "Outdoor unit modulation", "Modulatie buitenunit", "",
          0x434B, 0, "u8", 1, "%", None, precision=0),
    Extra("supply_voltage", "Outdoor unit supply voltage", "Voedingsspanning buitenunit",
          "HM096", B, 104, "i16", 1, "V", "voltage", precision=0, diagnostic=True),
    # --- water side ---
    Extra("water_flow", "Water flow", "Waterdebiet", "AM056",
          0x5083, 0, "u16", 100, "L/min", "volume_flow_rate", precision=1),
    Extra("odu_water_flow", "Outdoor unit water flow", "Waterdebiet buitenunit", "HM110",
          0x4385, 0, "u16", 100, "L/min", "volume_flow_rate", precision=1),
    Extra("pump_speed", "Pump speed", "Pomptoerental", "AM010",
          B, 76, "i16", 10, "%", None, precision=0),
    Extra("odu_pump_modulation", "Outdoor unit pump modulation", "Modulatie pomp buitenunit",
          "HM123", 0x439B, 0, "u16", 10, "%", None, precision=0),
    # --- temperatures ---
    _t("hp_flow_setpoint", "Heat pump flow setpoint", "Setpunt aanvoer warmtepomp", "HM003", B, 2),
    _t("hp_return_temperature", "Heat pump return temperature", "Retourtemperatuur warmtepomp",
       "HM002", 0x4302, 0),
    _t("average_flow_temperature", "Average flow temperature", "Gemiddelde aanvoertemperatuur",
       "HM020", 0x4314, 0),
    _t("odu_flow_temperature", "Outdoor unit flow temperature", "Aanvoertemperatuur buitenunit",
       "HM185", B, 14),
    _t("odu_air_temperature", "Outdoor unit air temperature", "Luchttemperatuur buitenunit",
       "HM098", 0x4377, 0),
    _t("evaporator_temperature", "Evaporator temperature", "Verdampertemperatuur", "", B, 28),
    _t("suction_temperature", "Compressor suction temperature", "Zuiggastemperatuur compressor",
       "", B, 24),
    _t("discharge_temperature", "Compressor discharge temperature", "Persgastemperatuur compressor",
       "", B, 26),
    _t("inverter_temperature", "Inverter temperature", "Invertertemperatuur", "HM094", B, 10,
       diagnostic=True),
    _t("zone_flow_setpoint", "Zone flow setpoint", "Setpunt aanvoer zone", "CM070", B, 42),
    _t("room_temperature", "Room temperature", "Kamertemperatuur", "CM030", 0x5404, 1, 10),
    _t("room_setpoint", "Room setpoint", "Gewenste kamertemperatuur", "CM190", 0x5419, 1, 10),
    _t("calculated_room_setpoint", "Calculated room setpoint", "Berekende kamertemperatuur",
       "CM280", 0x5436, 1),
    # --- other ---
    Extra("fan_speed", "Outdoor fan speed", "Ventilatortoerental buitenunit", "",
          B, 58, "i16", 1, "rpm", None, precision=0),
    Extra("eev_opening", "Expansion valve opening", "Opening expansieventiel", "",
          B, 62, "i16", 1, None, None, precision=0, diagnostic=True),
    Extra("seasonal_efficiency", "Seasonal efficiency", "Seizoensrendement", "AC083",
          0x5147, 1, "u16", 100, None, None, precision=2),
    # --- energy (cooling) ---
    _count("energy_consumed_cooling", "Electricity used cooling", "Stroomverbruik koelen",
           "AC089", 0x512E, 1, 10, "kWh", "energy"),
    _count("energy_delivered_cooling", "Cooling delivered", "Koeling geleverd", "",
           0x5087, 0, 1, "kWh", "energy"),
    # --- counters ---
    _count("compressor_hours", "Compressor hours", "Draaiuren compressor", "PC003",
           0x530C, unit="h", dc="duration"),
    _count("compressor_starts", "Compressor starts", "Starts compressor", "PC002", 0x530B),
    _count("heating_hours", "Heating hours", "Uren verwarmen", "PC000",
           0x5300, unit="h", dc="duration"),
    _count("power_on_hours", "Power-on hours", "Uren aan", "", 0x5000, unit="h", dc="duration",
           diagnostic=True),
    _count("pump_hours", "Pump hours", "Draaiuren pomp", "", 0x50AD, unit="h", dc="duration",
           diagnostic=True),
    _count("pump_starts", "Pump starts", "Starts pomp", "", 0x50AE, diagnostic=True),
    _count("backup_heater_hours", "Backup heater hours", "Uren elektrisch element", "",
           0x50AF, unit="h", dc="duration"),
    _count("backup_heater_starts", "Backup heater starts", "Starts elektrisch element", "",
           0x50B1),
    _count("defrost_cycles", "Defrost cycles", "Aantal ontdooicycli", "HC011", 0x43C2),
    _count("defrost_duration", "Defrost duration", "Ontdooiduur", "HC010", 0x43C1,
           diagnostic=True),
    # --- settings (read only) ---
    Extra("heating_curve_slope", "Heating curve slope", "Stooklijn helling", "CP230",
          0x3416, 1, "u8", 10, None, None, precision=1, diagnostic=True),
    Extra("heating_curve_base", "Heating curve base point", "Stooklijn voetpunt", "CP210",
          0x3414, 1, "u16", 10, "°C", "temperature", precision=1, diagnostic=True),
    Extra("max_flow_temperature", "Maximum flow temperature", "Maximale aanvoertemperatuur",
          "CP000", 0x3401, 1, "u16", 100, "°C", "temperature", precision=1, diagnostic=True),
    Extra("low_pressure_warning", "Low water pressure warning", "Waarschuwing lage waterdruk",
          "AP058", 0x302B, 0, "u8", 10, "bar", "pressure", precision=1, diagnostic=True),
    # --- on/off ---
    _flag("compressor_running", "Compressor running", "Compressor aan", "HM008", 0x4308,
          dc="running"),
    _flag("compressor_requested", "Compressor requested", "Compressor gevraagd", "HM030", 0x431E),
    _flag("pump_running", "Pump running", "Pomp aan", "AM015", 0x5012, dc="running"),
    _flag("defrosting", "Defrosting", "Ontdooien", "HM009", 0x4309, dc="running"),
    _flag("heat_pump_error", "Heat pump error", "Storing warmtepomp", "HM007", 0x4307,
          dc="problem"),
    _flag("frost_protection", "Frost protection", "Vorstbeveiliging", "", 0x502E, 1),
    _flag("heating_enabled", "Heating enabled", "Verwarmen ingeschakeld", "", 0x502E, 7),
)

BY_KEY = {e.key: e for e in EXTRAS}
DEFAULT_KEYS = [e.key for e in EXTRAS if e.default]

_NONE = {"i16": 0x8000, "u16": 0xFFFF, "u8": 0xFF, "u32": 0xFFFFFFFF}
_SIZE = {"i16": 2, "u16": 2, "u8": 1, "u32": 4, "bool": 1}


def decode(extra: Extra, data: bytes | None) -> float | bool | None:
    """Turn the raw bytes of one datapoint into a value (None = not available)."""
    size = _SIZE[extra.vtype]
    if not data or len(data) < size:
        return None
    if extra.vtype == "bool":
        return data[0] != 0
    if extra.vtype == "u32":
        raw = uint32(data)
        if raw is None:
            return None
        return raw if extra.scale == 1 else round(raw / extra.scale, 3)
    raw = int.from_bytes(data[:size], "little")
    if raw == _NONE[extra.vtype]:
        return None
    if extra.vtype == "i16" and raw >= 0x8000:
        raw -= 0x10000
    if extra.scale == 1:
        return raw
    return round(raw / extra.scale, 3)


def block_bytes(extra: Extra, block: bytes) -> bytes | None:
    """Slice the bytes of a block datapoint out of the 0x501d monitoring block."""
    end = extra.sub + _SIZE[extra.vtype]
    return block[extra.sub:end] if len(block) >= end else None
