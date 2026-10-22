"""Oligo data type and the shared oligo layout: [primer_f | index | payload | CRC16 | primer_r].

Framing works at the byte level. A *frame* is `index (big-endian) + payload + CRC16(index+payload)`.
Each codec then maps frame bytes to nucleotides in its own way.

The byte stream that gets framed is `u64 length + data`, so the decoder learns how many frames
to expect from frame 0 alone, independent of whatever `data` contains.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field

from .crc import crc16_bytes, crc16_ok

CRC_BYTES = 2
_LEN_PREFIX = struct.Struct(">Q")


class FramingError(ValueError):
    pass


class MissingOligosError(FramingError):
    """Some frames never arrived (dropout) or all their copies failed the CRC.

    Phase 3's Reed-Solomon layer turns these indices into erasures instead of failing."""

    def __init__(self, missing: list[int], expected: int | None):
        self.missing = missing
        self.expected = expected
        shown = missing[:10]
        more = f" (+{len(missing) - 10} more)" if len(missing) > 10 else ""
        super().__init__(f"missing oligo indices {shown}{more} of {expected if expected is not None else '?'}")


@dataclass
class Oligo:
    index: int
    sequence: str  # full nucleotide string, primers included
    codec: str = ""
    copy_id: int = 0
    meta: dict = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.sequence)


@dataclass(frozen=True)
class OligoLayout:
    payload_bytes: int = 16
    index_bytes: int = 3
    forward_primer: str = ""
    reverse_primer: str = ""

    def __post_init__(self) -> None:
        if self.payload_bytes < 8:
            raise ValueError("payload_bytes must be >= 8 (frame 0 carries the u64 length prefix)")
        if not 1 <= self.index_bytes <= 4:
            raise ValueError("index_bytes must be 1..4")
        for p in (self.forward_primer, self.reverse_primer):
            if set(p) - set("ACGT"):
                raise ValueError(f"primer {p!r} contains non-ACGT characters")

    @property
    def frame_bytes(self) -> int:
        return self.index_bytes + self.payload_bytes + CRC_BYTES

    @property
    def max_frames(self) -> int:
        return 2 ** (8 * self.index_bytes)

    def payload_efficiency(self) -> float:
        """Share of each frame that carries user payload (index and CRC are overhead)."""
        return self.payload_bytes / self.frame_bytes


@dataclass(frozen=True)
class ParsedFrame:
    index: int
    payload: bytes
    crc_ok: bool  # DETECTION result only; False means "do not trust index or payload"


def stream_chunks(data: bytes, payload_bytes: int) -> list[bytes]:
    """`u64 length + data`, cut into zero-padded chunks of payload_bytes."""
    stream = _LEN_PREFIX.pack(len(data)) + data
    n = max(1, math.ceil(len(stream) / payload_bytes))
    return [stream[i * payload_bytes : (i + 1) * payload_bytes].ljust(payload_bytes, b"\x00") for i in range(n)]


def chunks_to_data(chunks: list[bytes], data_len: int | None = None) -> bytes:
    stream = b"".join(chunks)
    if data_len is None:
        (data_len,) = _LEN_PREFIX.unpack(stream[: _LEN_PREFIX.size])
    return stream[_LEN_PREFIX.size : _LEN_PREFIX.size + data_len].ljust(data_len, b"\x00")


def make_frame(index: int, chunk: bytes, layout: OligoLayout) -> bytes:
    body = index.to_bytes(layout.index_bytes, "big") + chunk
    return body + crc16_bytes(body)


def build_frames(data: bytes, layout: OligoLayout, extra_chunks: list[bytes] | None = None) -> list[bytes]:
    """Frames for the data chunks, followed by any extra (e.g. RS parity) chunks."""
    chunks = stream_chunks(data, layout.payload_bytes) + list(extra_chunks or [])
    if len(chunks) > layout.max_frames:
        raise FramingError(
            f"{len(chunks)} frames needed but index_bytes={layout.index_bytes} allows {layout.max_frames}"
        )
    return [make_frame(i, c, layout) for i, c in enumerate(chunks)]


def parse_frame(frame: bytes, layout: OligoLayout) -> ParsedFrame:
    if len(frame) != layout.frame_bytes:
        raise FramingError(f"frame is {len(frame)} bytes, expected {layout.frame_bytes}")
    body, check = frame[:-CRC_BYTES], frame[-CRC_BYTES:]
    return ParsedFrame(
        index=int.from_bytes(body[: layout.index_bytes], "big"),
        payload=body[layout.index_bytes :],
        crc_ok=crc16_ok(body, check),
    )


def expected_frame_count(first_payload: bytes, layout: OligoLayout) -> int:
    if len(first_payload) < _LEN_PREFIX.size:
        # length prefix spans more than one frame only when payload_bytes < 8
        raise FramingError("payload_bytes must be >= 8 so frame 0 carries the length prefix")
    (length,) = _LEN_PREFIX.unpack(first_payload[: _LEN_PREFIX.size])
    return max(1, math.ceil((length + _LEN_PREFIX.size) / layout.payload_bytes))


def assemble(payloads: dict[int, bytes], layout: OligoLayout) -> bytes:
    """Reassemble the original data from {index: payload} of CRC-valid frames."""
    if 0 not in payloads:
        raise MissingOligosError([0], None)
    expected = expected_frame_count(payloads[0], layout)
    missing = [i for i in range(expected) if i not in payloads]
    if missing:
        raise MissingOligosError(missing, expected)
    stream = b"".join(payloads[i] for i in range(expected))
    (length,) = _LEN_PREFIX.unpack(stream[: _LEN_PREFIX.size])
    return stream[_LEN_PREFIX.size : _LEN_PREFIX.size + length]
