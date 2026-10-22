"""Raw 2-bit reference mapping (00→A, 01→C, 10→G, 11→T).

NOT Church. This is the theoretical density ceiling (2 bits/nt) with no biochemical constraint
handling, kept only as a reference point for density comparisons. The reference demo labelled
this mapping "Church"; Church et al. 2012 actually used 1 bit/nt (see codecs/church.py, Phase 2).
"""

from __future__ import annotations

import numpy as np

from ..codec_base import CodecStatus, FrameCodec, register_codec

_BASES = np.frombuffer(b"ACGT", dtype=np.uint8)
_LOOKUP = np.full(256, 255, dtype=np.uint8)
for _i, _b in enumerate(b"ACGT"):
    _LOOKUP[_b] = _i


@register_codec
class Raw2BitCodec(FrameCodec):
    name = "raw2bit"
    label = "Raw 2-bit (ceiling)"
    default_payload_bytes = 32
    status = CodecStatus.IMPLEMENTED
    description = "Density-ceiling reference: 2 bits/nt, no constraint handling. Not a published scheme."
    reference = "Baseline quaternary mapping (no citation)"
    nominal_bits_per_nt = 2.0

    def frame_to_nt(self, frame: bytes) -> str:
        b = np.frombuffer(frame, dtype=np.uint8)
        dibits = np.stack([(b >> 6) & 3, (b >> 4) & 3, (b >> 2) & 3, b & 3], axis=1).ravel()
        return _BASES[dibits].tobytes().decode("ascii")

    def nt_to_frame(self, core: str) -> bytes | None:
        if len(core) != 4 * self.layout.frame_bytes:
            return None
        vals = _LOOKUP[np.frombuffer(core.encode("ascii", errors="replace"), dtype=np.uint8)]
        if (vals == 255).any():
            return None
        v = vals.reshape(-1, 4)
        return ((v[:, 0] << 6) | (v[:, 1] << 4) | (v[:, 2] << 2) | v[:, 3]).astype(np.uint8).tobytes()
