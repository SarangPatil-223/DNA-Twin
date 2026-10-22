"""Yin-Yang style codec (simplified): two bits per nucleotide from two rules.

Yang rule: bit 1 of the pair picks the group — 0 -> {A, T}, 1 -> {C, G}.
Yin rule: bit 2 picks the base inside the group, and the mapping flips with the previous base,
so decoding always works from the received sequence alone.

Constraint screening (simplified): Ping et al. search segment pairings and 1,536 rule sets. Here
each frame is XOR-whitened with one of 16 fixed masks; the first mask whose sequence satisfies
GC 40-60 % and homopolymer <= 4 is used and its id is written in a 2-nt prefix.

Reference: Ping et al., Nature Computational Science 2 (2022), 234-242.
"""

from __future__ import annotations

import random

import numpy as np

from ..codec_base import CodecStatus, FrameCodec, register_codec
from ..constraints import gc_content, max_homopolymer

_B = "ACGT"
_PREFIX_LOOKUP = {b: i for i, b in enumerate(_B)}
_GROUP = {0: ("A", "T"), 1: ("C", "G")}
N_MASKS = 16
GC_RANGE = (0.40, 0.60)
MAX_RUN = 4


def _yin_flip(prev: str) -> int:
    return 0 if prev in "AG" else 1


def _mask(mask_id: int, n: int) -> bytes:
    if mask_id == 0:
        return bytes(n)
    return random.Random(0x5EED0000 + mask_id).randbytes(n)


@register_codec
class YinYangCodec(FrameCodec):
    name = "yinyang"
    label = "Yin-Yang 2022"
    status = CodecStatus.SIMPLIFIED
    description = "2 bits/nt via yang (group) + yin (base, depends on previous) rules; mask screening for GC/homopolymers."
    reference = "Ping et al. Towards practical and robust DNA-based data archiving using the yin-yang codec system. Nat Comput Sci 2022."
    nominal_bits_per_nt = 2.0
    default_payload_bytes = 32

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._masks = [_mask(i, self.layout.frame_bytes) for i in range(N_MASKS)]

    @staticmethod
    def _yy(frame: bytes) -> str:
        bits = np.unpackbits(np.frombuffer(frame, dtype=np.uint8))
        half = len(bits) // 2
        yang, yin = bits[:half], bits[half:]
        prev, out = "A", []
        for g, s in zip(yang, yin):
            base = _GROUP[int(g)][int(s) ^ _yin_flip(prev)]
            out.append(base)
            prev = base
        return "".join(out)

    def frame_to_nt(self, frame: bytes) -> str:
        best, best_score = "", None
        for mid, m in enumerate(self._masks):
            body = self._yy(bytes(a ^ b for a, b in zip(frame, m)))
            seq = _B[mid >> 2] + _B[mid & 3] + body
            gc, hp = gc_content(seq), max_homopolymer(seq)
            if GC_RANGE[0] <= gc <= GC_RANGE[1] and hp <= MAX_RUN:
                return seq
            score = abs(gc - 0.5) + max(0, hp - MAX_RUN)
            if best_score is None or score < best_score:
                best, best_score = seq, score
        return best

    def nt_to_frame(self, core: str) -> bytes | None:
        if len(core) != 2 + 4 * self.layout.frame_bytes or set(core) - set(_B):
            return None
        mid = (_PREFIX_LOOKUP[core[0]] << 2) | _PREFIX_LOOKUP[core[1]]
        body = core[2:]
        yang, yin = [], []
        prev = "A"
        for base in body:
            g = 1 if base in "CG" else 0
            s = _GROUP[g].index(base) ^ _yin_flip(prev)
            yang.append(g)
            yin.append(s)
            prev = base
        raw = np.packbits(np.array(yang + yin, dtype=np.uint8)).tobytes()
        return bytes(a ^ b for a, b in zip(raw, self._masks[mid]))
