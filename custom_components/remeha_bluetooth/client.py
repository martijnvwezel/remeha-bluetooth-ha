"""Session on top of a connected (and bonded) BleakClient.

Runs the two handshakes and reads objects. No Home Assistant imports.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

from bleak import BleakClient

from . import protocol as P

_LOGGER = logging.getLogger(__name__)

REQ = "496b1b03-cebc-4d59-9c32-14ea88c266f9"
RSP = "ab9af948-fb86-492d-820d-bdea2dcb7ecf"
PRE_TRIGGER = "94e54dc4-f69a-4c0c-8a6f-cc8f3135c665"
PRE_CHAL = "69092300-a182-4fea-803b-24ada406da8a"
PRE_RESP = "f1ca5aeb-02cd-44a8-972b-44b6e7250d0b"
PRE_ACK = "e2c47825-6dff-4d79-b74a-5bdc4f4661cf"


class AuthError(Exception):
    """A handshake with the gateway failed."""


# 0x501d sub 0 element 1: (key, byte offset, divisor)
BLOCK = [
    ("cop", 56, 1000),
    ("outdoor_temperature", 12, 100),
    ("flow_temperature", 4, 100),
    ("heat_pump_flow_temperature", 8, 100),
    ("return_temperature", 16, 100),
    ("flow_setpoint", 0, 100),
    ("dhw_temperature", 18, 100),
    ("dhw_setpoint", 22, 100),
    ("water_pressure", 40, 100),
]

# Counters read by index: (key, index, sub, divisor)
COUNTERS = [
    ("energy_consumed_total", 0x512F, 1, 10),
    ("energy_consumed_heating", 0x512C, 1, 10),
    ("energy_consumed_dhw", 0x512D, 1, 10),
    ("energy_delivered_total", 0x5089, 0, 1),
    ("energy_delivered_heating", 0x5085, 0, 1),
    ("energy_delivered_dhw", 0x5086, 0, 1),
]


@dataclass
class RemehaData:
    values: dict[str, float | None] = field(default_factory=dict)


class RemehaSession:
    def __init__(self, client: BleakClient) -> None:
        self._c = client
        self._rsp: asyncio.Queue[bytes] = asyncio.Queue()
        self._chal: asyncio.Queue[bytes] = asyncio.Queue()
        self._ack: asyncio.Queue[bytes] = asyncio.Queue()

    async def _notify(self, uuid: str, queue: asyncio.Queue) -> None:
        def cb(_char, data: bytearray) -> None:
            queue.put_nowait(bytes(data))

        for attempt in range(3):
            try:
                await self._c.start_notify(uuid, cb)
                return
            except Exception as err:  # noqa: BLE001
                # CCCD may already be enabled from a previous session
                if "UNLIKELY" in str(err).upper() or attempt == 2:
                    _LOGGER.debug("start_notify %s: %s (continuing)", uuid[:8], err)
                    return
                await asyncio.sleep(0.5)

    async def _write(self, uuid: str, data: bytes) -> None:
        await self._c.write_gatt_char(uuid, data, response=True)

    @staticmethod
    def _drain(q: asyncio.Queue) -> None:
        while not q.empty():
            q.get_nowait()

    async def authenticate(self) -> None:
        """Subscribe, pre-auth handshake, STL session handshake."""
        await self._notify(RSP, self._rsp)
        await self._notify(PRE_CHAL, self._chal)
        await self._notify(PRE_ACK, self._ack)
        await asyncio.sleep(0.3)

        # 1) GATT pre-auth
        await self._write(PRE_TRIGGER, b"")
        try:
            chal = await asyncio.wait_for(self._chal.get(), 5)
            await self._write(PRE_RESP, P.preauth_reply(chal))
            ack = await asyncio.wait_for(self._ack.get(), 5)
        except asyncio.TimeoutError as err:
            raise AuthError("No answer on pre-auth") from err
        if ack != b"\x01":
            raise AuthError(f"Pre-auth refused ({ack.hex()})")

        # 2) STL session
        self._drain(self._rsp)
        await self._write(REQ, P.HS_OPEN)
        challenge = None
        try:
            for _ in range(4):
                challenge = P.stl_challenge(await asyncio.wait_for(self._rsp.get(), 5))
                if challenge:
                    break
            if not challenge:
                raise AuthError("No session challenge")
            await self._write(REQ, P.stl_auth_reply(challenge))
            await asyncio.wait_for(self._rsp.get(), 5)
            await self._write(REQ, P.HS_FINISH)
            await asyncio.wait_for(self._rsp.get(), 5)
        except asyncio.TimeoutError as err:
            raise AuthError("Session handshake timed out") from err
        _LOGGER.debug("Session open")

    async def read(self, index: int, sub: int = 0, element: int = 1,
                   timeout: float = 4.0) -> bytes | None:
        """Read one object; returns its data bytes or None on timeout."""
        self._drain(self._rsp)
        asm = P.Reassembler()
        await self._write(REQ, P.build_read(index, sub, element))
        want = bytes([(index >> 8) & 0xFF, index & 0xFF, sub & 0xFF])
        deadline = time.monotonic() + timeout
        while (left := deadline - time.monotonic()) > 0:
            try:
                pkt = await asyncio.wait_for(self._rsp.get(), max(0.1, left))
            except asyncio.TimeoutError:
                break
            out = asm.feed(pkt)
            if out is None:
                continue
            header, data = out
            if len(header) >= 11 and header[8:11] == want:
                return data
            asm.reset()  # stale reply from an earlier read
        return None

    async def read_all(self) -> RemehaData:
        """Read everything the integration exposes."""
        values: dict[str, float | None] = {}
        block = await self.read(0x501D, 0, 1)
        if block is None or len(block) < 60:
            raise AuthError("No monitoring data from the gateway")
        for key, off, div in BLOCK:
            raw = P.int16_at(block, off)
            values[key] = None if raw is None else round(raw / div, 3)
        # Byte 78 = AM012 appliance status, byte 79 = AM014 sub status
        # (verified live: 3/30 while heating, 4/30 while making hot water).
        if len(block) > 79:
            values["status_code"] = None if block[78] == 0xFF else block[78]
            values["substatus_code"] = None if block[79] == 0xFF else block[79]
        for key, index, sub, div in COUNTERS:
            raw = P.uint32(await self.read(index, sub, 1, timeout=3) or b"")
            values[key] = None if raw is None else round(raw / div, 2)
        # Average COP since installation = heat delivered / electricity used
        # (the 0x508a SPF object returns no value on this firmware).
        used, made = values.get("energy_consumed_total"), values.get("energy_delivered_total")
        values["spf"] = round(made / used, 2) if used and made is not None else None
        return RemehaData(values)
