"""BLE bonding with the 6-digit PIN through BlueZ (Linux / Home Assistant OS).

bleak cannot answer a passkey request, so we register a tiny BlueZ agent on
D-Bus that returns the PIN, then call org.bluez.Device1.Pair ourselves.

NOTE: no `from __future__ import annotations` here: dbus_fast reads the
D-Bus signatures ("o", "u", "s") from the method annotations.
"""

import asyncio
import logging
import uuid

from dbus_fast import BusType, Message, MessageType, Variant
from dbus_fast.aio import MessageBus
from dbus_fast.service import ServiceInterface, method

_LOGGER = logging.getLogger(__name__)

BLUEZ = "org.bluez"


class PairingError(Exception):
    """Pairing failed for a generic reason."""


class InvalidPin(PairingError):
    """The gateway rejected the PIN."""


class _Agent(ServiceInterface):
    def __init__(self, pin: str) -> None:
        super().__init__("org.bluez.Agent1")
        self._pin = pin

    @method()
    def Release(self):  # noqa: N802
        pass

    @method()
    def RequestPinCode(self, device: "o") -> "s":  # noqa: N802,F821
        _LOGGER.debug("PIN code requested by %s", device)
        return self._pin

    @method()
    def RequestPasskey(self, device: "o") -> "u":  # noqa: N802,F821
        _LOGGER.debug("Passkey requested by %s", device)
        return int(self._pin)

    @method()
    def DisplayPasskey(self, device: "o", passkey: "u", entered: "q"):  # noqa: N802,F821
        pass

    @method()
    def DisplayPinCode(self, device: "o", pincode: "s"):  # noqa: N802,F821
        pass

    @method()
    def RequestConfirmation(self, device: "o", passkey: "u"):  # noqa: N802,F821
        pass

    @method()
    def RequestAuthorization(self, device: "o"):  # noqa: N802,F821
        pass

    @method()
    def AuthorizeService(self, device: "o", uuid: "s"):  # noqa: N802,F821
        pass

    @method()
    def Cancel(self):  # noqa: N802
        _LOGGER.debug("Pairing cancelled by BlueZ")


def _dev_suffix(address: str) -> str:
    return "dev_" + address.upper().replace(":", "_")


async def _call(bus, path, interface, member, signature="", body=None, timeout=None):
    msg = Message(
        destination=BLUEZ, path=path, interface=interface, member=member,
        signature=signature, body=body or [],
    )
    if timeout:
        reply = await asyncio.wait_for(bus.call(msg), timeout)
    else:
        reply = await bus.call(msg)
    if reply.message_type == MessageType.ERROR:
        detail = reply.body[0] if reply.body else ""
        raise PairingError(f"{reply.error_name}: {detail}")
    return reply


async def _device_paths(bus, address: str) -> list[tuple[str, bool]]:
    """All BlueZ object paths for this address (one per adapter) + Paired."""
    reply = await _call(bus, "/", "org.freedesktop.DBus.ObjectManager",
                        "GetManagedObjects")
    suffix = _dev_suffix(address)
    out = []
    for path, ifaces in reply.body[0].items():
        dev = ifaces.get("org.bluez.Device1")
        if dev and path.endswith(suffix):
            paired = dev.get("Paired")
            out.append((path, bool(paired.value) if paired else False))
    return out


async def async_is_paired(address: str) -> bool:
    bus = await MessageBus(bus_type=BusType.SYSTEM, negotiate_unix_fd=False).connect()
    try:
        return any(p for _, p in await _device_paths(bus, address))
    finally:
        bus.disconnect()


async def async_ensure_paired(address: str, pin: str, device_path: str | None = None,
                              timeout: float = 40.0) -> None:
    """Bond with the gateway using the PIN, unless it is already bonded.

    Raises InvalidPin when the PIN is refused, PairingError otherwise.
    """
    pin = "".join(c for c in str(pin) if c.isdigit())
    if len(pin) != 6:
        raise InvalidPin("PIN must be 6 digits")

    bus = await MessageBus(bus_type=BusType.SYSTEM, negotiate_unix_fd=False).connect()
    agent_path = f"/remeha_bluetooth/agent_{uuid.uuid4().hex[:8]}"
    registered = False
    try:
        paths = await _device_paths(bus, address)
        if any(p for _, p in paths):
            _LOGGER.debug("%s already bonded", address)
            return
        if device_path is None:
            if not paths:
                raise PairingError("Device not known to BlueZ (not seen yet)")
            device_path = paths[0][0]

        bus.export(agent_path, _Agent(pin))
        await _call(bus, "/org/bluez", "org.bluez.AgentManager1", "RegisterAgent",
                    "os", [agent_path, "KeyboardOnly"])
        registered = True
        await _call(bus, "/org/bluez", "org.bluez.AgentManager1",
                    "RequestDefaultAgent", "o", [agent_path])

        _LOGGER.info("Bonding with %s", address)
        try:
            await _call(bus, device_path, "org.bluez.Device1", "Pair",
                        timeout=timeout)
        except PairingError as err:
            text = str(err)
            if "AlreadyExists" in text:
                return
            if "AuthenticationFailed" in text or "AuthenticationRejected" in text:
                raise InvalidPin(text) from err
            raise
        except asyncio.TimeoutError as err:
            raise PairingError("Pairing timed out") from err

        # Trust the device so reconnects never ask again.
        try:
            await _call(bus, device_path, "org.freedesktop.DBus.Properties", "Set",
                        "ssv", ["org.bluez.Device1", "Trusted", Variant("b", True)])
        except PairingError as err:
            _LOGGER.debug("Could not set Trusted: %s", err)
    finally:
        if registered:
            try:
                await _call(bus, "/org/bluez", "org.bluez.AgentManager1",
                            "UnregisterAgent", "o", [agent_path])
            except PairingError:
                pass
        bus.disconnect()


async def async_remove_bond(address: str) -> None:
    """Forget the bond (used when the user removes the integration)."""
    bus = await MessageBus(bus_type=BusType.SYSTEM, negotiate_unix_fd=False).connect()
    try:
        for path, _ in await _device_paths(bus, address):
            adapter = path.rsplit("/", 1)[0]
            try:
                await _call(bus, adapter, "org.bluez.Adapter1", "RemoveDevice",
                            "o", [path])
            except PairingError as err:
                _LOGGER.debug("RemoveDevice failed: %s", err)
    finally:
        bus.disconnect()
