"""Retrieval metrics. Every number here is computed from a run; nothing is estimated."""

from __future__ import annotations

import numpy as np

from .binary import read_header


def byte_accuracy(orig: bytes, got: bytes | None) -> float | None:
    if got is None:
        return None
    if not orig:
        return 1.0 if not got else 0.0
    n = min(len(orig), len(got))
    a = np.frombuffer(orig[:n], dtype=np.uint8)
    b = np.frombuffer(got[:n], dtype=np.uint8)
    return float((a == b).sum()) / len(orig)


def bit_accuracy(orig: bytes, got: bytes | None) -> float | None:
    if got is None:
        return None
    if not orig:
        return 1.0 if not got else 0.0
    n = min(len(orig), len(got))
    a = np.unpackbits(np.frombuffer(orig[:n], dtype=np.uint8))
    b = np.unpackbits(np.frombuffer(got[:n], dtype=np.uint8))
    return float((a == b).sum()) / (8 * len(orig))


def payload_slice(original_container: bytes, recovered_container: bytes) -> bytes | None:
    """Cut the file payload out of a recovered container using the ORIGINAL header length.
    Used for partial-accuracy metrics when the recovered header itself is damaged.
    Only meaningful for uncompressed containers."""
    meta, hdr, plen = read_header(original_container)
    if meta.compressed:
        return None
    return recovered_container[hdr : hdr + plen]


def sequence_stats(seqs: list[str]) -> dict:
    total = sum(len(s) for s in seqs)
    gc = sum(s.count("G") + s.count("C") for s in seqs)
    return {"n_oligos": len(seqs), "total_nt": total, "oligo_len": len(seqs[0]) if seqs else 0,
            "gc": gc / total if total else 0.0}
