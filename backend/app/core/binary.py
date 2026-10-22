"""Lossless bytes <-> bits conversion and the DNA Twin container format.

The container wraps the user's file with a metadata header so that the decoder can recover the
filename, MIME type, original size and SHA-256 from the DNA itself, without the database.

Container layout (all integers big-endian):

    magic         4 bytes   b"DNTW"
    version       u8        CONTAINER_VERSION
    flags         u8        bit0 = payload is zlib-compressed
    codec_id      u8 len  + utf-8
    filename      u16 len + utf-8   (basename only, max 255 bytes)
    mime          u8 len  + utf-8
    original_size u64       size of the original file
    payload_len   u64       size of the (possibly compressed) payload that follows
    sha256        32 bytes  SHA-256 of the ORIGINAL file bytes
    header_crc    u16       CRC-16 over every header byte above (detection only)
    payload       payload_len bytes

The container is self-delimiting: bytes after the payload (oligo padding) are ignored.
"""

from __future__ import annotations

import hashlib
import struct
import zlib
from dataclasses import dataclass

import numpy as np

from .crc import crc16

MAGIC = b"DNTW"
CONTAINER_VERSION = 1
FLAG_COMPRESSED = 0x01
_MAX_FILENAME_BYTES = 255


class ContainerError(ValueError):
    """The container is structurally unreadable (bad magic, truncated, header CRC failure)."""


@dataclass(frozen=True)
class FileMetadata:
    filename: str
    mime: str
    original_size: int
    sha256: str  # hex
    codec_id: str
    compressed: bool
    version: int = CONTAINER_VERSION


@dataclass(frozen=True)
class UnpackResult:
    metadata: FileMetadata
    data: bytes  # recovered file bytes (may be wrong if sha256_ok is False)
    sha256_ok: bool
    sha256_got: str
    header_bytes: int
    payload_len: int


# --------------------------------------------------------------------------- bits


def bytes_to_bits(data: bytes) -> np.ndarray:
    """MSB-first bit array (dtype uint8, values 0/1). Lossless."""
    return np.unpackbits(np.frombuffer(data, dtype=np.uint8))


def bits_to_bytes(bits: np.ndarray | list[int]) -> bytes:
    """Inverse of bytes_to_bits. Bit length must be a multiple of 8."""
    arr = np.asarray(bits, dtype=np.uint8)
    if arr.size % 8:
        raise ValueError(f"bit length {arr.size} is not a multiple of 8")
    if arr.size and arr.max() > 1:
        raise ValueError("bit array contains values other than 0/1")
    return np.packbits(arr).tobytes()


# --------------------------------------------------------------------------- helpers


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sanitize_filename(name: str) -> str:
    """Basename only, no control chars, truncated to 255 UTF-8 bytes on a char boundary."""
    base = name.replace("\\", "/").split("/")[-1]
    base = "".join(ch for ch in base if ch.isprintable()).strip().lstrip(".") or "file"
    encoded = base.encode("utf-8")[:_MAX_FILENAME_BYTES]
    return encoded.decode("utf-8", errors="ignore")


# --------------------------------------------------------------------------- container


def pack_container(
    data: bytes,
    filename: str,
    mime: str = "application/octet-stream",
    codec_id: str = "none",
    compress: bool = False,
) -> bytes:
    """Wrap `data` in a metadata header. Compression is only applied if it actually shrinks the data."""
    payload = data
    flags = 0
    if compress:
        candidate = zlib.compress(data, level=9)
        if len(candidate) < len(data):
            payload, flags = candidate, FLAG_COMPRESSED

    fname = sanitize_filename(filename).encode("utf-8")
    mime_b = mime.encode("utf-8")[:255]
    codec_b = codec_id.encode("utf-8")[:255]

    header = bytearray(MAGIC)
    header += struct.pack(">BB", CONTAINER_VERSION, flags)
    header += struct.pack(">B", len(codec_b)) + codec_b
    header += struct.pack(">H", len(fname)) + fname
    header += struct.pack(">B", len(mime_b)) + mime_b
    header += struct.pack(">QQ", len(data), len(payload))
    header += hashlib.sha256(data).digest()
    header += struct.pack(">H", crc16(bytes(header)))
    return bytes(header) + payload


def _take(buf: bytes, pos: int, n: int) -> tuple[bytes, int]:
    if pos + n > len(buf):
        raise ContainerError(f"container truncated at byte {pos} (needed {n} more)")
    return buf[pos : pos + n], pos + n


def read_header(blob: bytes) -> tuple[FileMetadata, int, int]:
    """Parse the header. Returns (metadata, header_length, payload_len)."""
    pos = 0
    magic, pos = _take(blob, pos, 4)
    if magic != MAGIC:
        raise ContainerError(f"bad magic {magic!r}")
    raw, pos = _take(blob, pos, 2)
    version, flags = struct.unpack(">BB", raw)
    if version != CONTAINER_VERSION:
        raise ContainerError(f"unsupported container version {version}")
    raw, pos = _take(blob, pos, 1)
    codec_b, pos = _take(blob, pos, raw[0])
    raw, pos = _take(blob, pos, 2)
    (n,) = struct.unpack(">H", raw)
    fname_b, pos = _take(blob, pos, n)
    raw, pos = _take(blob, pos, 1)
    mime_b, pos = _take(blob, pos, raw[0])
    raw, pos = _take(blob, pos, 16)
    original_size, payload_len = struct.unpack(">QQ", raw)
    digest, pos = _take(blob, pos, 32)
    stored_crc, pos = _take(blob, pos, 2)
    if crc16(blob[: pos - 2]) != int.from_bytes(stored_crc, "big"):
        raise ContainerError("header CRC mismatch — header is corrupted")

    meta = FileMetadata(
        filename=fname_b.decode("utf-8", errors="replace"),
        mime=mime_b.decode("utf-8", errors="replace"),
        original_size=original_size,
        sha256=digest.hex(),
        codec_id=codec_b.decode("utf-8", errors="replace"),
        compressed=bool(flags & FLAG_COMPRESSED),
        version=version,
    )
    return meta, pos, payload_len


def unpack_container(blob: bytes) -> UnpackResult:
    """Recover the original file. Never raises on a hash mismatch — reports it via sha256_ok,
    so callers can still measure partial accuracy. Raises ContainerError if unreadable."""
    meta, hdr_len, payload_len = read_header(blob)
    payload, _ = _take(blob, hdr_len, payload_len)
    if meta.compressed:
        try:
            data = zlib.decompress(payload)
        except zlib.error as exc:
            raise ContainerError(f"compressed payload is corrupted: {exc}") from exc
    else:
        data = payload
    got = sha256_hex(data)
    return UnpackResult(
        metadata=meta,
        data=data,
        sha256_ok=(got == meta.sha256 and len(data) == meta.original_size),
        sha256_got=got,
        header_bytes=hdr_len,
        payload_len=payload_len,
    )
