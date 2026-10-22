"""Reed-Solomon OUTER code across oligos — ERROR CORRECTION.

Layout: data frames are grouped into blocks of `k` frames. For every byte column j of the payload,
the k bytes at column j form an RS message over GF(256); the `r` parity bytes go into r parity
frames appended after all data frames. A lost oligo (dropout, or CRC failure from the DETECTION
layer) is an *erasure* at a known position, and RS repairs up to r erasures per block.

Block sizing keeps k + r <= 255 (the GF(256) codeword limit).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from reedsolo import ReedSolomonError, RSCodec


@dataclass(frozen=True)
class RSPlan:
    n_data: int
    parity_pct: float
    k: int  # data frames per block
    r: int  # parity frames per block

    @property
    def n_blocks(self) -> int:
        return math.ceil(self.n_data / self.k) if self.n_data and self.r else 0

    @property
    def n_parity(self) -> int:
        return self.n_blocks * self.r

    def block_data_range(self, b: int) -> range:
        return range(b * self.k, min(self.n_data, (b + 1) * self.k))

    def block_parity_range(self, b: int) -> range:
        start = self.n_data + b * self.r
        return range(start, start + self.r)


def plan(n_data: int, parity_pct: float) -> RSPlan:
    if parity_pct <= 0 or n_data == 0:
        return RSPlan(n_data, 0.0, max(n_data, 1), 0)
    if parity_pct > 300:
        raise ValueError("parity_pct above 300% is not supported")
    k = min(n_data, max(1, math.floor(255 / (1 + parity_pct / 100))))
    r = max(1, math.ceil(k * parity_pct / 100))
    while k + r > 255:
        k -= 1
        r = max(1, math.ceil(k * parity_pct / 100))
    return RSPlan(n_data, parity_pct, k, r)


def encode_parity(chunks: list[bytes], p: RSPlan) -> list[bytes]:
    """Parity chunks (same length as data chunks), in plan order."""
    if p.r == 0:
        return []
    width = len(chunks[0])
    rs = RSCodec(p.r)
    out: list[bytes] = []
    for b in range(p.n_blocks):
        block = [chunks[i] for i in p.block_data_range(b)]
        cols = [rs.encode(bytes(c[j] for c in block))[len(block):] for j in range(width)]
        out.extend(bytes(cols[j][t] for j in range(width)) for t in range(p.r))
    return out


@dataclass
class RSStats:
    blocks: int = 0
    erasures: int = 0  # data+parity frames missing before correction
    recovered_frames: int = 0  # data frames rebuilt by RS
    unrecoverable_frames: list[int] = field(default_factory=list)  # data frames still missing
    failed_blocks: list[int] = field(default_factory=list)


def decode(payloads: dict[int, bytes], p: RSPlan, width: int) -> tuple[list[bytes | None], RSStats]:
    """Return one entry per data frame (None if unrecoverable) plus correction stats."""
    stats = RSStats(blocks=p.n_blocks)
    data: list[bytes | None] = [payloads.get(i) for i in range(p.n_data)]
    stats.erasures = sum(x is None for x in data) + sum(
        1 for b in range(p.n_blocks) for i in p.block_parity_range(b) if i not in payloads
    )
    if p.r == 0:
        stats.unrecoverable_frames = [i for i, x in enumerate(data) if x is None]
        return data, stats

    rs = RSCodec(p.r)
    for b in range(p.n_blocks):
        drange, prange = p.block_data_range(b), p.block_parity_range(b)
        missing_data = [i for i in drange if data[i] is None]
        if not missing_data:
            continue
        positions = list(drange) + list(prange)
        erase = [pos for pos, idx in enumerate(positions) if idx not in payloads]
        if len(erase) > p.r:
            stats.failed_blocks.append(b)
            stats.unrecoverable_frames.extend(missing_data)
            continue
        zero = bytes(width)
        rebuilt = [bytearray(width) for _ in missing_data]
        try:
            for j in range(width):
                word = bytearray(payloads.get(idx, zero)[j] for idx in positions)
                msg = rs.decode(word, erase_pos=erase)[0]
                for n, i in enumerate(missing_data):
                    rebuilt[n][j] = msg[i - drange.start]
        except ReedSolomonError:
            stats.failed_blocks.append(b)
            stats.unrecoverable_frames.extend(missing_data)
            continue
        for n, i in enumerate(missing_data):
            data[i] = bytes(rebuilt[n])
        stats.recovered_frames += len(missing_data)
    return data, stats
