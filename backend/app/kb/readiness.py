"""LLM readiness: how usable is the data that came back out of DNA, for an LLM?

The LLM never sees DNA — it sees recovered text. So "which codec suits LLMs" reduces to measurable
properties of the recovered data (EVALUATION ONLY — the original is used here as ground truth and
is never ingested into the knowledge base):
  text_similarity   1 - normalized edit distance between recovered and original extracted text
  chunk_intact      share of original chunks reproduced exactly in the recovered text
  retrieval_overlap for probe questions built from the original, overlap of the top-k chunks
                    retrieved from the recovered index vs the original index
  readiness         0-100 = 100 * (0.4 * text_similarity + 0.3 * chunk_intact + 0.3 * retrieval_overlap)
"""
from __future__ import annotations

import random

import numpy as np
from rapidfuzz.distance import Levenshtein

from .extract import chunk_text, clean, extract_pages
from .providers import HashingEmbedder

_EMB = HashingEmbedder(384)


def _text(data: bytes | None, mime: str, filename: str) -> str:
    return clean(" ".join(t for _, t in extract_pages(data, mime, filename)))


def llm_readiness(original: bytes, recovered: bytes | None, mime: str, filename: str,
                  chunk_size: int = 120, k: int = 3, probes: int = 8) -> dict:
    orig_text = _text(original, mime, filename)
    if not orig_text:
        return {"extractable": False, "readiness": None, "reason": "no extractable text in the original"}
    rec_text = _text(recovered, mime, filename) if recovered else ""
    sim = 1.0 - Levenshtein.normalized_distance(orig_text[:200_000], rec_text[:200_000]) if rec_text else 0.0

    oc = [c["text"] for c in chunk_text([(None, orig_text)], chunk_size, chunk_size // 10)]
    rc = [c["text"] for c in chunk_text([(None, rec_text)], chunk_size, chunk_size // 10)] if rec_text else []
    rset = set(rc)
    intact = sum(c in rset for c in oc) / len(oc) if oc else 0.0

    overlap = 0.0
    if rc and oc:
        rng = random.Random(0)
        words = orig_text.split()
        qs = []
        for _ in range(probes):
            s = rng.randrange(0, max(1, len(words) - 12))
            qs.append(" ".join(words[s : s + 12]))
        qv = _EMB.embed(qs)
        ov, rv = _EMB.embed(oc), _EMB.embed(rc)
        hits = []
        for i in range(len(qs)):
            top_o = [oc[j] for j in np.argsort(-(ov @ qv[i]))[:k]]
            top_r = [rc[j] for j in np.argsort(-(rv @ qv[i]))[:k]]
            # a recovered chunk "matches" an original chunk if they are near-identical text
            m = sum(any(Levenshtein.normalized_distance(a, b) < 0.05 for b in top_r) for a in top_o)
            hits.append(m / len(top_o))
        overlap = float(np.mean(hits))
    score = 100 * (0.4 * sim + 0.3 * intact + 0.3 * overlap)
    return {"extractable": True, "text_similarity": round(sim, 4), "chunk_intact": round(intact, 4),
            "retrieval_overlap": round(overlap, 4), "readiness": round(score, 1),
            "original_chars": len(orig_text), "recovered_chars": len(rec_text)}


def readiness_extra(original: bytes, recovered: bytes | None, mime: str, filename: str = "") -> dict:
    """Adapter for benchmark rows (keys prefixed llm_)."""
    r = llm_readiness(original, recovered, mime, filename)
    if not r.get("extractable"):
        return {}
    return {"llm_readiness": r["readiness"], "llm_text_similarity": r["text_similarity"],
            "llm_chunk_intact": r["chunk_intact"], "llm_retrieval_overlap": r["retrieval_overlap"]}
