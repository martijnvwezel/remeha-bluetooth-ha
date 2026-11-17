from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.remeha_bluetooth import protocol as P
from custom_components.remeha_bluetooth.client import RemehaData, RemehaSession
from custom_components.remeha_bluetooth.const import DOMAIN
from custom_components.remeha_bluetooth.pairing import InvalidPin

ADDR = "00:80:E1:11:22:33"


def _info():
    from bleak.backends.device import BLEDevice
    from bleak.backends.scanner import AdvertisementData
    adv = AdvertisementData(local_name="EHC-16_1", manufacturer_data={}, service_data={},
                            service_uuids=[], tx_power=None, rssi=-80, platform_data=())
    dev = BLEDevice(ADDR, "EHC-16_1", {"path": "/org/bluez/hci0/dev_00_80_E1_11_22_33"})
    return BluetoothServiceInfoBleak(name="EHC-16_1", address=ADDR, rssi=-80,
        manufacturer_data={}, service_data={}, service_uuids=[], source="local",
        device=dev, advertisement=adv, connectable=True, time=0, tx_power=None)


VALUES = {"cop": 3.21, "outdoor_temperature": 7.5, "energy_consumed_total": 230.5}


def _session():
    client = MagicMock(); client.disconnect = AsyncMock(); client.is_connected = True
    s = MagicMock(); s.read_all = AsyncMock(return_value=RemehaData(dict(VALUES)))
    return client, s


async def test_bluetooth_flow_creates_entry(hass):
    with patch("custom_components.remeha_bluetooth.config_flow.async_open_session",
               AsyncMock(return_value=_session())):
        r = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_BLUETOOTH}, data=_info())
        assert r["type"] is FlowResultType.FORM and r["step_id"] == "pin"
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {"pin": "12345"})
        assert r["errors"] == {"base": "pin_format"}
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {"pin": "123 456"})
    assert r["type"] is FlowResultType.CREATE_ENTRY
    assert r["data"] == {"address": ADDR, "pin": "123456", "serial": "1"}
    assert r["title"] == "Heat pump"


async def test_flow_wrong_pin(hass):
    with patch("custom_components.remeha_bluetooth.config_flow.async_open_session",
               AsyncMock(side_effect=InvalidPin("x"))):
        r = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_BLUETOOTH}, data=_info())
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {"pin": "000000"})
    assert r["errors"] == {"base": "invalid_pin"}


async def test_user_flow_no_devices(hass):
    r = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert r["type"] is FlowResultType.ABORT and r["reason"] == "no_devices_found"


async def test_setup_creates_sensors(hass):
    entry = MockConfigEntry(domain=DOMAIN, unique_id=ADDR, title="EHC-16_1",
                            data={"address": ADDR, "pin": "123456"})
    entry.add_to_hass(hass)
    with patch("custom_components.remeha_bluetooth.coordinator.async_open_session",
               AsyncMock(return_value=_session())):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    states = {s.entity_id: s.state for s in hass.states.async_all("sensor")}
    print(states)
    assert states["sensor.heat_pump_cop"] == "3.21"
    assert states["sensor.heat_pump_electricity_used_total"] == "230.5"
    assert states["sensor.heat_pump_water_pressure"] == "unknown"


class FakeClient:
    """Plays the gateway: answers handshakes and reads like the real device."""
    def __init__(self, block: bytes, counters: dict):
        self.cbs = {}; self.block = block; self.counters = counters
    async def start_notify(self, uuid, cb): self.cbs[uuid] = cb
    def _n(self, uuid, data): self.cbs[uuid](None, bytearray(data))
    async def write_gatt_char(self, uuid, data, response=True):
        from custom_components.remeha_bluetooth import client as C
        if uuid == C.PRE_TRIGGER: self._n(C.PRE_CHAL, bytes(8))
        elif uuid == C.PRE_RESP: self._n(C.PRE_ACK, b"\x01")
        elif data == P.HS_OPEN: self._n(C.RSP, bytes.fromhex("ff01020100020103") + bytes(8) + b"\0\0")
        elif data[:8].hex() == "ff01020100020203" or data == P.HS_FINISH: self._n(C.RSP, b"\xff\x01")
        else:
            idx, sub = data[9:11], data[11]
            index = int.from_bytes(idx, "big")
            payload = self.block if index == 0x501D else self.counters.get(index, b"\x00\x00\x02\x06")
            msg = bytes([1, 2, 0, 0, 0, 1, 0, 1]) + idx + bytes([sub]) + payload
            chunks = [msg[i:i + 19] for i in range(0, len(msg), 19)]
            self._n(C.RSP, bytes([0, 0, 0]) + bytes(11))  # stale reply for other index
            self._n(C.RSP, b"\xff\x00")
            for i, ch in enumerate(chunks): self._n(C.RSP, bytes([i]) + ch)
            self._n(C.RSP, b"\xff\x00\x00")


async def test_session_decodes():
    block = bytearray(b"\x00\x80" * 61)
    block[56:58] = (3210).to_bytes(2, "little", signed=True)
    block[12:14] = (-525).to_bytes(2, "little", signed=True)
    fc = FakeClient(bytes(block), {0x512F: (2305).to_bytes(4, "little"), 0x5089: (840).to_bytes(4, "little")})
    s = RemehaSession(fc)
    await s.authenticate()
    d = (await s.read_all()).values
    assert d["cop"] == 3.21 and d["outdoor_temperature"] == -5.25
    assert d["energy_consumed_total"] == 230.5 and d["water_pressure"] is None
    assert d["energy_delivered_total"] == 840 and d["spf"] == 3.64
    assert d["energy_delivered_dhw"] is None
