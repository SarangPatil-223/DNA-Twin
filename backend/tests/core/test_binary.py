import numpy as np
import pytest

from app.core.binary import (ContainerError, bits_to_bytes, bytes_to_bits, pack_container,
                             read_header, sanitize_filename, sha256_hex, unpack_container)


def test_bits_roundtrip(sample):
    _, _, data = sample
    bits = bytes_to_bits(data)
    assert bits.size == 8 * len(data)
    assert set(np.unique(bits)).issubset({0, 1})
    assert bits_to_bytes(bits) == data


def test_bits_msb_first():
    assert list(bytes_to_bits(b"\x80\x01")) == [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1]


def test_bits_rejects_bad_input():
    with pytest.raises(ValueError):
        bits_to_bytes([1, 0, 1])
    with pytest.raises(ValueError):
        bits_to_bytes([2] * 8)


@pytest.mark.parametrize("compress", [False, True])
def test_container_roundtrip(sample, compress):
    name, mime, data = sample
    blob = pack_container(data, name, mime, "raw2bit", compress=compress)
    res = unpack_container(blob + b"\x00" * 37)  # trailing padding must be ignored
    assert res.data == data and res.sha256_ok
    m = res.metadata
    assert (m.filename, m.mime, m.original_size, m.sha256, m.codec_id) == (name, mime, len(data), sha256_hex(data), "raw2bit")


def test_compression_only_when_it_helps():
    rnd = bytes(np.random.default_rng(0).integers(0, 256, 4000, dtype=np.uint8))
    assert not read_header(pack_container(rnd, "r.bin", compress=True))[0].compressed
    assert read_header(pack_container(b"A" * 4000, "a.txt", compress=True))[0].compressed


def test_payload_corruption_reported_not_raised():
    blob = bytearray(pack_container(b"hello world" * 10, "h.txt"))
    blob[-5] ^= 0xFF
    res = unpack_container(bytes(blob))
    assert not res.sha256_ok and res.sha256_got != res.metadata.sha256


def test_header_corruption_detected():
    blob = bytearray(pack_container(b"hello", "h.txt"))
    blob[10] ^= 0x01
    with pytest.raises(ContainerError):
        unpack_container(bytes(blob))


def test_truncation_and_bad_magic():
    blob = pack_container(b"hello" * 20, "h.txt")
    with pytest.raises(ContainerError):
        unpack_container(blob[:-10])
    with pytest.raises(ContainerError):
        unpack_container(b"XXXX" + blob[4:])


@pytest.mark.parametrize("raw,expected", [
    ("../../etc/passwd", "passwd"), ("C:\\x\\evil.pdf", "evil.pdf"), ("", "file"),
    (".hidden", "hidden"), ("a\x00b\nc.txt", "abc.txt"),
])
def test_sanitize_filename(raw, expected):
    assert sanitize_filename(raw) == expected


def test_long_unicode_filename_truncated_on_char_boundary():
    name = "é" * 300 + ".txt"
    out = sanitize_filename(name)
    assert len(out.encode()) <= 255
    out.encode("utf-8")  # still valid
