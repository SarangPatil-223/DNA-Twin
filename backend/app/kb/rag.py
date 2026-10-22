"""Knowledge base over RECOVERED data only.

Every chunk comes out of a retrieval run (DNA -> decode). The original upload is never ingested.
Chunk payload carries {doc_id, chunk_id, source_file, page, recovered_exact, codec, ...} so each
answer can say which codec its evidence came through and whether that recovery was byte-exact.
"""
from __future__ import annotations

import pathlib
import time
import uuid

import numpy as np
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import SIMULATION_LABEL
from app.core.channel import ChannelParams
from app.db import models as M
from app.services import runs

from . import store
from .extract import chunk_text, extract_pages
from .providers import get_embedder, get_llm

SYSTEM = (
    "You answer questions using ONLY the numbered sources, which are text recovered from a SIMULATED "
    "DNA data-storage pipeline. Cite every claim with its source tag like [S1]. If the sources do not "
    "contain the answer, say so plainly. If a source is marked POSSIBLY CORRUPTED, warn that the text "
    "may contain decoding errors. Do not claim the data was stored in real DNA."
)

DEFAULT_LAZY_CHANNEL = dict(sub=0.0018, ins=0.0001, dele=0.0006, copies=5, dropout=0.01, seed=7)


def _collection():
    emb = get_embedder()
    name = store.collection_name(emb.name, emb.dim)
    store.ensure(name, emb.dim)
    return emb, name


def ingest(db: Session, retrieval_run_id: int, chunk_size: int = 500, overlap: int = 50) -> M.KBDocument:
    rr = db.get(M.RetrievalRun, retrieval_run_id)
    if rr is None:
        raise HTTPException(404, f"retrieval run {retrieval_run_id} not found — the knowledge base only "
                                 "accepts data that came out of a DNA retrieval run")
    existing = db.scalars(select(M.KBDocument).where(M.KBDocument.retrieval_run_id == rr.id)).first()
    if existing:
        if existing.embedding == get_embedder().name:
            return existing
        # the embedding provider changed since this document was indexed: rebuild its vectors
        for ch in db.scalars(select(M.KBChunk).where(M.KBChunk.doc_id == existing.id)).all():
            db.delete(ch)
        db.delete(existing)
        db.flush()
    f = db.get(M.File, rr.file_id)
    if not rr.recovered_path or not pathlib.Path(rr.recovered_path).exists():
        raise HTTPException(422, "this retrieval run produced no recoverable bytes to ingest")
    data = pathlib.Path(rr.recovered_path).read_bytes()
    mime = "image/png" if f.kind == "image" else f.mime
    pages = extract_pages(data, mime, f.filename if f.kind != "image" else "recovered.png")
    chunks = chunk_text(pages, chunk_size, overlap)
    if not chunks:
        raise HTTPException(422, "no text could be extracted from the recovered data"
                                 + (" (for images this needs OCR text in the picture)" if f.kind == "image" else ""))
    emb, coll = _collection()
    doc = M.KBDocument(retrieval_run_id=rr.id, file_id=f.id, codec=rr.codec, source_file=f.filename,
                       recovered_exact=rr.exact_match, n_chunks=len(chunks), embedding=emb.name)
    db.add(doc)
    db.flush()
    vecs = emb.embed([c["text"] for c in chunks])
    ids = [str(uuid.uuid4()) for _ in chunks]
    payloads = [{"doc_id": doc.id, "chunk_id": c["chunk_idx"], "source_file": f.filename, "page": c["page"],
                 "recovered_exact": rr.exact_match, "codec": rr.codec, "retrieval_run_id": rr.id,
                 "file_id": f.id, "text": c["text"]} for c in chunks]
    store.upsert(coll, ids, vecs, payloads)
    for c, pid in zip(chunks, ids):
        db.add(M.KBChunk(doc_id=doc.id, chunk_idx=c["chunk_idx"], page=c["page"], text=c["text"],
                         token_count=c["token_count"], qdrant_point_id=pid))
    db.commit()
    db.refresh(doc)
    return doc


def lazy_document(db: Session, file_id: int, codec: str, params: dict | None = None,
                  channel: dict | None = None) -> tuple[M.KBDocument, dict]:
    """Lazy retrieval: decode this file from the virtual DNA store only when a question needs it,
    then cache the result (the retrieval run and the KB document are reused next time)."""
    info = {"cached": True, "decode_ms": None}
    ch = ChannelParams(**{**DEFAULT_LAZY_CHANNEL, **(channel or {})})
    want = ch.to_dict()
    keys = ("sub", "ins", "dele", "dropout", "copies", "seed", "years")
    rr = None
    for cand in db.scalars(select(M.RetrievalRun).where(M.RetrievalRun.file_id == file_id, M.RetrievalRun.codec == codec)
                           .order_by(M.RetrievalRun.id.desc())).all():
        sim = db.get(M.SimulationRun, cand.simulation_run_id)
        if channel is None or (sim and all(abs(float(sim.params.get(k, 0)) - float(want[k])) < 1e-12 for k in keys)):
            rr = cand  # without an explicit channel any cached recovery of this codec is reused
            break
    if rr is None:
        t0 = time.perf_counter()
        rr = runs.full_run(db, file_id, codec, params or ({"overhead": 0.4} if codec == "fountain" else {"rs_parity_pct": 20}
                                                            if codec in ("church", "yinyang", "raw2bit") else {}), ch)
        info = {"cached": False, "decode_ms": round((time.perf_counter() - t0) * 1000, 1), "channel": ch.to_dict()}
    doc = ingest(db, rr.id)
    info.update({"retrieval_run_id": rr.id, "recovered_exact": rr.exact_match})
    return doc, info


def query(db: Session, question: str, doc_ids: list[int] | None = None, top_k: int = 5) -> dict:
    if not question.strip():
        raise HTTPException(400, "question is empty")
    emb, coll = _collection()
    t0 = time.perf_counter()
    hits = store.search(coll, emb.embed([question])[0], top_k, doc_ids)
    search_ms = (time.perf_counter() - t0) * 1000
    warnings: list[str] = []
    if not hits:
        return {"label": SIMULATION_LABEL, "answer": "No recovered documents are in the knowledge base for this scope yet.",
                "citations": [], "warnings": ["knowledge base is empty for this scope"], "provider": None}
    blocks, cites = [], []
    for i, h in enumerate(hits, 1):
        tag = f"S{i}"
        flag = "" if h.get("recovered_exact") else " (POSSIBLY CORRUPTED: recovery was not byte-exact)"
        blocks.append(f"[{tag}] (file {h['source_file']}, via {h['codec']} codec{flag})\n{h['text']}")
        cites.append({"tag": tag, "doc_id": h["doc_id"], "chunk_id": h["chunk_id"], "codec": h["codec"],
                      "source_file": h["source_file"], "page": h.get("page"), "score": round(h["score"], 4),
                      "recovered_exact": h.get("recovered_exact"), "retrieval_run_id": h.get("retrieval_run_id"),
                      "snippet": h["text"][:400]})
    if any(not c["recovered_exact"] for c in cites):
        warnings.append("Some sources come from a recovery that was NOT byte-exact; the answer may be built on corrupted text.")
    llm = get_llm()
    prompt = "\n\n".join(blocks) + f"\n\nQUESTION: {question}"
    t1 = time.perf_counter()
    try:
        answer = llm.generate(SYSTEM, prompt)
    except Exception as exc:  # fall back rather than failing the request
        from .providers import ExtractiveProvider

        warnings.append(f"LLM provider {llm.name} failed ({type(exc).__name__}); showing extractive answer instead.")
        llm = ExtractiveProvider()
        answer = llm.generate(SYSTEM, prompt)
    if not llm.is_llm:
        warnings.append("No LLM is configured (set GEMINI_API_KEY or ANTHROPIC_API_KEY, or run Ollama); answer is extractive.")
    return {"label": SIMULATION_LABEL, "answer": answer, "citations": cites, "warnings": warnings,
            "provider": llm.name, "embedding": emb.name, "search_ms": round(search_ms, 1),
            "llm_ms": round((time.perf_counter() - t1) * 1000, 1)}


def compare(db: Session, file_id: int, question: str, codecs: list[str], top_k: int = 4,
            channel: dict | None = None) -> dict:
    """Ask the same question through several codecs: each answer only sees text that came back
    through that codec. Shows directly how storage choice changes what an LLM can answer."""
    rows = []
    for c in codecs:
        doc, info = lazy_document(db, file_id, c, channel=channel)
        res = query(db, question, [doc.id], top_k)
        rr = db.get(M.RetrievalRun, info["retrieval_run_id"])
        rows.append({"codec": c, "doc_id": doc.id, "lazy": info, "llm_readiness": rr.llm_readiness,
                     "exact_match": rr.exact_match, **res})
    return {"label": SIMULATION_LABEL, "question": question, "results": rows, "channel": channel or "cached / high-fidelity"}


def top_score(scores: list[float]) -> float:
    return float(np.max(scores)) if scores else 0.0
