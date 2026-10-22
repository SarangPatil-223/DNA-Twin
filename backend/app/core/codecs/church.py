"""Church et al. 2012 style: 1 bit per nucleotide (A/C = 0, G/T = 1).

The free choice between the two bases for each bit is used, as in the paper, to avoid
homopolymers and balance GC: pick the base that moves running GC toward 50 %, unless that would
extend a run past `max_run`. Decoding needs no side information: A/C -> 0 and G/T -> 1 always.

Reference: Church, Gao & Kosuri, Science 337:1628 (2012). The paper's 159-nt oligo carried
96 nt data + 19 nt address + 2 x 22 nt primers; here index and CRC16 are bytes inside the frame.
"""

from __future__ import annotations

import numpy as np

from ..codec_base import CodecStatus, FrameCodec, register_codec

_ZERO = ("A", "C")  # (AT option, GC option)
_ONE = ("T", "G")
_LUT = np.full(256, 255, dtype=np.uint8)
for _b, _v in (("A", 0), ("C", 0), ("G", 1), ("T", 1)):
    _LUT[ord(_b)] = _v


@register_codec
class ChurchCodec(FrameCodec):
    name = "church"
    label = "Church 2012"
    status = CodecStatus.IMPLEMENTED
    description = "1 bit/nt; free base choice balances GC and caps homopolymers at 3. Accuracy reference."
    reference = "Church, Gao & Kosuri. Next-generation digital information storage in DNA. Science 2012."
    nominal_bits_per_nt = 1.0
    default_payload_bytes = 16
    max_run = 3

    def frame_to_nt(self, frame: bytes) -> str:
        bits = np.unpackbits(np.frombuffer(frame, dtype=np.uint8))
        out: list[str] = []
        gc = 0
        run_base, run = "", 0
        for n, bit in enumerate(bits):
            at_opt, gc_opt = _ONE if bit else _ZERO
            # prefer GC when we are below 50 % so far (n counts bases already placed)
            first, second = (gc_opt, at_opt) if gc * 2 <= n else (at_opt, gc_opt)
            base = first
            if base == run_base and run >= self.max_run:
                base = second
            if base == run_base:
                run += 1
            else:
                run_base, run = base, 1
            gc += base in "GC"
            out.append(base)
        return "".join(out)

    def nt_to_frame(self, core: str) -> bytes | None:
        if len(core) != 8 * self.layout.frame_bytes:
            return None
        v = _LUT[np.frombuffer(core.encode("ascii", errors="replace"), dtype=np.uint8)]
        if (v == 255).any():
            return None
        return np.packbits(v).tobytes()
