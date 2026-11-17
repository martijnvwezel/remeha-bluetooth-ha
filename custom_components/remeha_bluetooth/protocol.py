"""Remeha EHC-16 BLE "STL" protocol: frames, CRC, TEA handshake, reassembly.

Pure Python, no Home Assistant or bleak imports, so it can be tested anywhere.
See spec_folder/SPEC.md in the repository for the full description.
"""

from __future__ import annotations

START = 0xFF
FUNC_READ = 0x02

_M = 0xFFFFFFFF
_K = 0x15EFA43F
_DELTA = 0x9E3779B9
AUTH_LEVEL = 4

# Fixed handshake frames (identical every session).
HS_OPEN = bytes.fromhex("ff0102010002000323d6")
HS_FINISH = bytes.fromhex("ff01020100000003ff582a00e544")


def crc16_modbus(data: bytes) -> int:
    """CRC-16/MODBUS."""
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc & 0xFFFF


def _frame(body: bytes) -> bytes:
    crc = crc16_modbus(body)
    return bytes([START]) + body + bytes([(crc >> 8) & 0xFF, crc & 0xFF])


def build_read(index: int, sub: int = 0, element: int = 1) -> bytes:
    """Read request for object index/sub (array element)."""
    body = bytes(
        [0x01, FUNC_READ, 0, 0, 0, 0, 0, element & 0xFF,
         (index >> 8) & 0xFF, index & 0xFF, sub & 0xFF]
    )
    return _frame(body)


def tea(challenge8: bytes, endian: str, level: int = AUTH_LEVEL) -> bytes:
    """TEA variant used by both handshakes (8 bytes -> 8 bytes, no key)."""
    v0 = int.from_bytes(challenge8[0:4], endian)
    v1 = int.from_bytes(challenge8[4:8], endian)
    a = b = level
    s = _DELTA
    for _ in range(32):
        a = (a + (((_K + ((b << 4) & _M)) & _M) ^ ((v0 + (b >> 5)) & _M)
                  ^ ((b + s) & _M))) & _M
        b = (b + (((v1 + ((a << 4) & _M)) & _M) ^ ((s + a) & _M)
                  ^ ((level + (a >> 5)) & _M))) & _M
        s = (s + _DELTA) & _M
    return a.to_bytes(4, endian) + b.to_bytes(4, endian)


def preauth_reply(challenge8: bytes) -> bytes:
    """Reply for the GATT pre-auth challenge: 0x04 + TEA little-endian."""
    return bytes([AUTH_LEVEL]) + tea(challenge8, "little")


def stl_auth_reply(challenge8: bytes) -> bytes:
    """Frame with the STL session auth reply (TEA big-endian)."""
    body = bytes.fromhex("01020100020203") + bytes([0xFF, AUTH_LEVEL]) + tea(
        challenge8, "big"
    )
    return _frame(body)


def stl_challenge(pkt: bytes) -> bytes | None:
    """Extract the 8-byte challenge from the HS_OPEN response."""
    if len(pkt) >= 17 and pkt[:8].hex() == "ff01020100020103":
        return pkt[8:16]
    return None


class Reassembler:
    """Collect fragmented notifications into (header, data)."""

    def __init__(self) -> None:
        self._frames: dict[int, bytes] = {}

    def reset(self) -> None:
        self._frames.clear()

    def feed(self, pkt: bytes) -> tuple[bytes, bytes] | None:
        if not pkt:
            return None
        if pkt[0] == START:
            if self._frames:
                ordered = b"".join(self._frames[i] for i in sorted(self._frames))
                self._frames.clear()
                return ordered[:11], ordered[11:]
            body = pkt[1:]
            if len(body) < 13:
                return body, b""
            return body[:11], body[11:-2]
        self._frames[pkt[0]] = pkt[1:]
        return None


# ---- value decoding ---------------------------------------------------------
def int16_at(data: bytes, off: int) -> int | None:
    """Signed int16 LE at offset; None for 'sensor not present'."""
    if len(data) < off + 2:
        return None
    raw = int.from_bytes(data[off:off + 2], "little", signed=True)
    if raw == -32768:
        return None
    return raw


def uint32(data: bytes) -> int | None:
    """Unsigned int32 LE counter; None for sentinels / placeholders."""
    if not data or len(data) < 4:
        return None
    if data[2:4] == b"\x02\x06":  # shared "no live value" placeholder
        return None
    raw = int.from_bytes(data[:4], "little")
    if raw in (0xFFFFFFFF, 0x7FFFFFFF, 0x80000000):
        return None
    return raw


if __name__ == "__main__":
    assert build_read(0x501D, 0, 1).hex() == "ff0102000000000001501d006fab"
    assert tea(bytes.fromhex("34294c40088aea6b"), "big").hex() == "ac7fe88bd97bf669"
    assert preauth_reply(bytes.fromhex("002e27e193d9030e")).hex() == "040400dcb8fc60cb65"
    print("protocol self-test OK")
