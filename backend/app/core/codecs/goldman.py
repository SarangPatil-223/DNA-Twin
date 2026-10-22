"""Goldman et al. 2013 style (simplified).

  bytes -> base-3 digits (6 trits per byte; the paper used a Huffman code with 5-6 trits/byte)
  -> 100-trit fragments starting every 25 trits, so each position is covered by up to 4 fragments
  -> each fragment gets 12 index trits + 1 parity trit
  -> rotating code: each trit picks one of the 3 bases that differ from the previous base,
     so there are no homopolymers by construction
  -> odd fragments are reverse-complemented; an orientation base is added at each end.

Decoding votes each trit position across the overlapping fragments (majority), which is what
lets Goldman survive a lost or damaged fragment. The parity trit only catches ~2/3 of damaged
fragments; the rest are out-voted.

Reference: Goldman et al., Nature 494:77-80 (2013).
"""

from __future__ import annotations

import math

import numpy as np

from ..codec_base import Codec, CodecStatus, DecodeReport, Manifest, register_codec
from ..oligo import MissingOligosError, Oligo, chunks_to_data, stream_chunks

BASES = "ACGT"
FRAG = 100
STEP = 25
IDX_TRITS = 12
TRITS_PER_BYTE = 6
_COMP = str.maketrans("ACGT", "TGCA")
_NEXT = {p: [b for b in BASES if b != p] for p in BASES}


def _rc(s: str) -> str:
    return s.translate(_COMP)[::-1]


def bytes_to_trits(data: bytes) -> np.ndarray:
    v = np.frombuffer(data, dtype=np.uint8).astype(np.int32)
    out = np.empty((len(v), TRITS_PER_BYTE), dtype=np.int8)
    for k in range(TRITS_PER_BYTE - 1, -1, -1):
        out[:, k] = v % 3
        v //= 3
    return out.ravel()


def trits_to_bytes(trits: np.ndarray) -> tuple[bytes, int]:
    t = trits.reshape(-1, TRITS_PER_BYTE).astype(np.int32)
    v = np.zeros(len(t), dtype=np.int32)
    for k in range(TRITS_PER_BYTE):
        v = v * 3 + t[:, k]
    overflow = int((v > 255).sum())
    return np.clip(v, 0, 255).astype(np.uint8).tobytes(), overflow


def _to_trits(n: int, width: int) -> list[int]:
    out = []
    for _ in range(width):
        out.append(n % 3)
        n //= 3
    return out[::-1]


def rotate_encode(trits, prev: str = "A") -> str:
    out = []
    for t in trits:
        b = _NEXT[prev][int(t)]
        out.append(b)
        prev = b
    return "".join(out)


def rotate_decode(seq: str, prev: str = "A") -> list[int] | None:
    out = []
    for b in seq:
        opts = _NEXT[prev]
        if b not in opts:
            return None  # homopolymer or illegal base: cannot be a valid rotating-code string
        out.append(opts.index(b))
        prev = b
    return out


@register_codec
class GoldmanCodec(Codec):
    name = "goldman"
    label = "Goldman 2013"
    status = CodecStatus.SIMPLIFIED
    description = "Base-3 rotating code (no homopolymers), 100-trit fragments overlapping by 75 for 4x coverage, majority vote."
    reference = "Goldman et al. Towards practical, high-capacity, low-maintenance information storage in synthesized DNA. Nature 2013."
    nominal_bits_per_nt = math.log2(3)

    def __init__(self, **_ignored):
        super().__init__()

    def encode(self, data: bytes) -> list[Oligo]:
        stream = b"".join(stream_chunks(data, 1))
        trits = bytes_to_trits(stream)
        n_frag = max(1, math.ceil((len(trits) - FRAG) / STEP) + 1) if len(trits) > FRAG else 1
        if n_frag > 3**IDX_TRITS:
            raise ValueError("file too large for 12 index trits")
        padded = np.zeros(STEP * (n_frag - 1) + FRAG, dtype=np.int8)
        padded[: len(trits)] = trits
        oligos = []
        for i in range(n_frag):
            body = [int(t) for t in padded[i * STEP : i * STEP + FRAG]] + _to_trits(i, IDX_TRITS)
            body.append(sum(body) % 3)  # parity trit
            core = rotate_encode(body, "A")
            seq = "A" + core + ("G" if core[-1] == "C" else "C")
            if i % 2:
                seq = _rc(seq)
            oligos.append(Oligo(index=i, sequence=seq, codec=self.name, meta={"rc": bool(i % 2)}))
        self.manifest = Manifest(self.name, len(data), n_frag, len(oligos),
                                 {"n_trits": int(len(trits)), "fragment": FRAG, "step": STEP})
        return oligos

    def decode(self, oligos: list[Oligo], manifest: Manifest | None = None, best_effort: bool = False) -> bytes:
        m = manifest or self.manifest
        if m is None:
            raise ValueError("Goldman decoding needs the manifest (fragment count and trit length)")
        rep = DecodeReport(received=len(oligos), ecc="4x overlap majority vote")
        n_frag, n_trits = m.n_units, int(m.params["n_trits"])
        total = STEP * (n_frag - 1) + FRAG
        votes = np.zeros((total, 3), dtype=np.int32)
        seen: set[int] = set()
        want = 1 + FRAG + IDX_TRITS + 1 + 1
        for o in oligos:
            s = o.sequence
            if len(s) != want or set(s) - set(BASES):
                rep.undecodable += 1
                continue
            if s[0] in "CG":  # reverse-complemented fragment
                s = _rc(s)
            if s[0] != "A":
                rep.undecodable += 1
                continue
            body = rotate_decode(s[1:-1], "A")
            if body is None:
                rep.undecodable += 1
                continue
            if sum(body[:-1]) % 3 != body[-1]:
                rep.crc_failures += 1  # parity trit = detection
                continue
            idx = 0
            for t in body[FRAG : FRAG + IDX_TRITS]:
                idx = idx * 3 + t
            if idx >= n_frag:
                rep.crc_failures += 1
                continue
            if idx in seen:
                rep.duplicates += 1
            seen.add(idx)
            pos = idx * STEP
            votes[np.arange(pos, pos + FRAG), body[:FRAG]] += 1
        rep.accepted = len(seen)
        covered = votes.sum(axis=1) > 0
        uncovered = [i for i in range(n_trits) if not covered[i]]
        trits = votes.argmax(axis=1).astype(np.int8)[:n_trits]
        rep.erasures = n_frag - len(seen)
        # count trit positions where the vote was not unanimous = corrections by voting
        tops = np.sort(votes[:n_trits], axis=1)
        rep.corrected_units = int(((tops[:, 1] > 0) & covered[:n_trits]).sum())
        stream, overflow = trits_to_bytes(trits[: n_trits - n_trits % TRITS_PER_BYTE])
        lost_bytes = sorted({i // TRITS_PER_BYTE for i in uncovered})
        rep.unrecoverable_units = lost_bytes
        rep.complete = not lost_bytes
        if overflow:
            rep.notes.append(f"{overflow} byte values out of range after voting (clamped)")
        self.last_report = rep
        if lost_bytes and not best_effort:
            raise MissingOligosError(sorted({min(n_frag - 1, (b * TRITS_PER_BYTE) // STEP) for b in lost_bytes}), n_frag)
        return chunks_to_data([stream], m.data_len)
