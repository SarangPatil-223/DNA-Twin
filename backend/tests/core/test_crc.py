from app.core.crc import crc16, crc16_bytes, crc16_ok


def test_check_value():
    assert crc16(b"123456789") == 0x29B1  # CRC-16/CCITT-FALSE standard check value


def test_detects_every_single_bit_flip():
    data = b"ACGT frame payload 0123456789"
    good = crc16_bytes(data)
    for i in range(len(data) * 8):
        flipped = bytearray(data)
        flipped[i // 8] ^= 1 << (i % 8)
        assert not crc16_ok(bytes(flipped), good), f"bit {i} flip went undetected"


def test_detects_burst_up_to_16_bits():
    data = bytearray(b"\x55" * 32)
    good = crc16_bytes(bytes(data))
    for start in range(0, 200, 7):
        for L in range(1, 17):
            d = bytearray(data)
            for k in range(start, start + L):
                d[k // 8] ^= 1 << (k % 8)
            assert not crc16_ok(bytes(d), good)
