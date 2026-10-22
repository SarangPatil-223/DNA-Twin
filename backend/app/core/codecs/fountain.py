"""DNA Fountain (simplified), after Erlich & Zielinski 2017.

  data -> K source segments of `segment_bytes`
  droplet(seed) = XOR of d segments, d drawn from a robust soliton distribution, segments picked
                  by a PRNG seeded with `seed`
  oligo = 2-bit map of [seed (4 B) | droplet payload | CRC16]
  screening: droplets whose DNA breaks GC 45-55 % or homopolymer <= 3 are thrown away and the
             next seed is tried, so every oligo meets the constraints by construction
  generate ceil(K * (1 + overhead)) valid droplets.

Decoding solves the XOR system over GF(2) (Gaussian elimination, which includes the peeling
solutions). Segments are whitened with a fixed keystream first (Erlich et al. encoded compressed,
high-entropy files), and each droplet payload is masked with a seed-derived keystream so small
files can still pass screening. Simplifications: CRC16 instead of the paper's per-droplet Reed-Solomon, K kept in
the manifest, PRNG is Python's Mersenne Twister, robust-soliton c/delta are our defaults.
"""

from __future__ import annotations

import math
import random

import numpy as np

from ..codec_base import Codec, CodecStatus, DecodeReport, Manifest, register_codec
from ..constraints import gc_content, max_homopolymer
from ..crc import crc16_bytes, crc16_ok
from ..oligo import MissingOligosError, Oligo, chunks_to_data, stream_chunks

_BASES = np.frombuffer(b"ACGT", dtype=np.uint8)
_LUT = np.full(256, 255, dtype=np.uint8)
for _i, _b in enumerate(b"ACGT"):
    _LUT[_b] = _i
SEED_BYTES = 4


def _to_nt(b: bytes) -> str:
    v = np.frombuffer(b, dtype=np.uint8)
    d = np.stack([(v >> 6) & 3, (v >> 4) & 3, (v >> 2) & 3, v & 3], axis=1).ravel()
    return _BASES[d].tobytes().decode()


def _from_nt(s: str) -> bytes | None:
    v = _LUT[np.frombuffer(s.encode("ascii", "replace"), dtype=np.uint8)]
    if (v == 255).any() or len(v) % 4:
        return None
    v = v.reshape(-1, 4)
    return ((v[:, 0] << 6) | (v[:, 1] << 4) | (v[:, 2] << 2) | v[:, 3]).astype(np.uint8).tobytes()


def robust_soliton_cdf(k: int, c: float = 0.1, delta: float = 0.05) -> list[float]:
    if k == 1:
        return [0.0, 1.0]
    rho = [0.0, 1.0 / k] + [1.0 / (d * (d - 1)) for d in range(2, k + 1)]
    s = c * math.log(k / delta) * math.sqrt(k)
    pivot = max(1, min(k, int(round(k / s)))) if s > 0 else k
    tau = [0.0] * (k + 1)
    for d in range(1, pivot):
        tau[d] = s / (k * d)
    if pivot <= k:
        tau[pivot] = s * math.log(s / delta) / k if s > delta else 0.0
    mu = [rho[d] + tau[d] for d in range(k + 1)]
    z = sum(mu)
    cdf, acc = [], 0.0
    for d in range(k + 1):
        acc += mu[d] / z
        cdf.append(acc)
    return cdf


def droplet_segments(seed: int, k: int, cdf: list[float]) -> list[int]:
    rng = random.Random(seed)
    u = rng.random()
    d = next((i for i, v in enumerate(cdf) if v >= u), k)
    d = max(1, min(k, d))
    return rng.sample(range(k), d)


def _whiten(chunks: list[bytes]) -> list[bytes]:
    """XOR each segment with a fixed pseudo-random keystream (self-inverse). Without this,
    low-entropy input (headers, zero padding, repetitive text) yields droplets that no seed can
    make pass the homopolymer screen, because the seed only changes 16 of ~150 nt."""
    out = []
    for i, c in enumerate(chunks):
        ks = random.Random(0xD1A7_0000 + i).randbytes(len(c))
        out.append(_xor(c, ks))
    return out


def _seed_keystream(seed: int, n: int) -> bytes:
    """Per-droplet keystream derived from the seed. With few source segments (small files) there
    are only a handful of distinct XOR payloads, and the seed field alone cannot move GC into the
    screening window; masking the payload by seed lets every new seed produce a new sequence."""
    return random.Random(seed ^ 0xA5A5A5A5).randbytes(n)


def _xor(a: bytes, b: bytes) -> bytes:
    return (int.from_bytes(a, "big") ^ int.from_bytes(b, "big")).to_bytes(len(a), "big")


@register_codec
class FountainCodec(Codec):
    name = "fountain"
    label = "DNA Fountain 2017"
    status = CodecStatus.SIMPLIFIED
    description = "LT fountain droplets, 2 bits/nt, screened for GC 45-55% and homopolymer <= 3; GF(2) decoding."
    reference = "Erlich & Zielinski. DNA Fountain enables a robust and efficient storage architecture. Science 2017."
    nominal_bits_per_nt = 2.0
    unit_bytes_param = "segment_bytes"
    gc_range = (0.45, 0.55)
    max_run = 3

    def __init__(self, segment_bytes: int = 32, overhead: float = 0.30, max_seed_tries: int = 200_000, **_ignored):
        super().__init__()
        if segment_bytes < 8:
            raise ValueError("segment_bytes must be >= 8")
        self.segment_bytes = segment_bytes
        self.overhead = overhead
        self.max_seed_tries = max_seed_tries

    def _droplet_nt(self, seed: int, segs: list[bytes], cdf) -> tuple[str, list[int]]:
        idx = droplet_segments(seed, len(segs), cdf)
        payload = segs[idx[0]]
        for i in idx[1:]:
            payload = _xor(payload, segs[i])
        body = seed.to_bytes(SEED_BYTES, "big") + _xor(payload, _seed_keystream(seed, len(payload)))
        return _to_nt(body + crc16_bytes(body)), idx

    def encode(self, data: bytes) -> list[Oligo]:
        segs = _whiten(stream_chunks(data, self.segment_bytes))
        k = len(segs)
        cdf = robust_soliton_cdf(k)
        target = math.ceil(k * (1 + self.overhead)) if k > 1 else 2
        oligos: list[Oligo] = []
        counter, tried, rejected = 1, 0, 0
        rank_pivots: dict[int, int] = {}
        # keep going past `target` until the droplets are decodable at zero noise (full GF(2) rank)
        while len(oligos) < target or len(rank_pivots) < k:
            if tried >= self.max_seed_tries:
                raise RuntimeError(f"only {len(oligos)} of {target} droplets passed screening after {tried} seeds")
            # spread counters over the 32-bit space (odd multiplier = bijection), like the paper's
            # LFSR seeds; small integers would write long A-runs into the seed field
            seed = (counter * 2654435761) & 0xFFFFFFFF
            nt, idx = self._droplet_nt(seed, segs, cdf)
            tried += 1
            if self.gc_range[0] <= gc_content(nt) <= self.gc_range[1] and max_homopolymer(nt) <= self.max_run:
                oligos.append(Oligo(index=len(oligos), sequence=nt, codec=self.name, meta={"seed": seed, "degree": len(idx)}))
                mask = 0
                for i in idx:
                    mask |= 1 << i
                while mask:
                    low = (mask & -mask).bit_length() - 1
                    if low in rank_pivots:
                        mask ^= rank_pivots[low]
                    else:
                        rank_pivots[low] = mask
                        break
            else:
                rejected += 1
            counter += 1
        self.manifest = Manifest(self.name, len(data), k, len(oligos),
                                 {"segment_bytes": self.segment_bytes, "overhead": self.overhead,
                                  "seeds_tried": tried, "screen_rejected": rejected})
        return oligos

    def decode(self, oligos: list[Oligo], manifest: Manifest | None = None, best_effort: bool = False) -> bytes:
        m = manifest or self.manifest
        if m is None:
            raise ValueError("Fountain decoding needs the manifest (K, segment size)")
        k, sb = m.n_units, int(m.params["segment_bytes"])
        cdf = robust_soliton_cdf(k)
        rep = DecodeReport(received=len(oligos), ecc="LT fountain / GF(2) elimination")
        want = 4 * (SEED_BYTES + sb + 2)
        pivots: dict[int, tuple[int, int]] = {}  # lowest col -> (mask, payload int)
        seen = set()
        for o in oligos:
            if len(o.sequence) != want:
                rep.undecodable += 1
                continue
            raw = _from_nt(o.sequence)
            if raw is None:
                rep.undecodable += 1
                continue
            body, chk = raw[:-2], raw[-2:]
            if not crc16_ok(body, chk):
                rep.crc_failures += 1
                continue
            seed = int.from_bytes(body[:SEED_BYTES], "big")
            if seed in seen:
                rep.duplicates += 1
                continue
            seen.add(seed)
            mask = 0
            for i in droplet_segments(seed, k, cdf):
                mask |= 1 << i
            pay = int.from_bytes(_xor(body[SEED_BYTES:], _seed_keystream(seed, sb)), "big")
            while mask:
                low = (mask & -mask).bit_length() - 1
                if low in pivots:
                    pm, pp = pivots[low]
                    mask ^= pm
                    pay ^= pp
                else:
                    pivots[low] = (mask, pay)
                    break
        rep.accepted = len(seen)
        solved: dict[int, int] = {}
        for col in sorted(pivots, reverse=True):
            mask, pay = pivots[col]
            rest = mask & ~(1 << col)
            ok = True
            while rest:
                low = (rest & -rest).bit_length() - 1
                if low not in solved:
                    ok = False
                    break
                pay ^= solved[low]
                rest &= rest - 1
            if ok:
                solved[col] = pay
        missing = [i for i in range(k) if i not in solved]
        rep.erasures = len(missing)
        rep.unrecoverable_units = missing
        rep.complete = not missing
        self.last_report = rep
        if missing and not best_effort:
            raise MissingOligosError(missing, k)
        segs = _whiten([solved.get(i, 0).to_bytes(sb, "big") for i in range(k)])
        return chunks_to_data(segs, m.data_len)
