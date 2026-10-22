"""CRC-16/CCITT-FALSE — ERROR DETECTION only.

A CRC tells you *that* an oligo is corrupted; it never repairs it. Frames that fail the CRC
are handed to the outer code (Reed-Solomon, Phase 3) as erasures.

Parameters: poly 0x1021, init 0xFFFF, no reflection, xorout 0x0000.
Check value for b"123456789" is 0x29B1.
"""

from __future__ import annotations

POLY = 0x1021
INIT = 0xFFFF


def _build_table() -> tuple[int, ...]:
    table = []
    for byte in range(256):
        crc = byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ POLY) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
        table.append(crc)
    return tuple(table)


_TABLE = _build_table()


def crc16(data: bytes, init: int = INIT) -> int:
    crc = init
    for b in data:
        crc = ((crc << 8) & 0xFFFF) ^ _TABLE[((crc >> 8) ^ b) & 0xFF]
    return crc


def crc16_bytes(data: bytes) -> bytes:
    return crc16(data).to_bytes(2, "big")


def crc16_ok(data: bytes, checksum: bytes) -> bool:
    return len(checksum) == 2 and crc16(data) == int.from_bytes(checksum, "big")
