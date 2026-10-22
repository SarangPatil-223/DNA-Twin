"""HTTP API. Thin layer over app.services / app.kb / app.recommend / app.reports."""
from __future__ import annotations

import pathlib

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import SIMULATION_LABEL, __version__, imaging
from app.core.benchmark import SweepConfig
from app.core.channel import ChannelParams
from app.core.codec_base import codec_class, list_codecs, runnable_codecs
from app.db import models as M
from app.db.session import get_db
from app.kb import rag
from app.kb.providers import get_embedder, get_llm
from app.recommend import PROFILES, dataset_csv, recommend
from app.reports import benchmark_pdf, research
from app.services import runs
from app.settings import get_settings

router = APIRouter()
L = SIMULATION_LABEL


# --------------------------------------------------------------------------- serializers

def ser_file(f: M.File) -> dict:
    return {"id": f.id, "filename": f.filename, "mime": f.mime, "size": f.size, "sha256": f.sha256, "kind": f.kind,
            "created_at": f.created_at.isoformat()}


def ser_enc(e: M.EncodingRun, sample: int = 0) -> dict:
    d = {"id": e.id, "file_id": e.file_id, "codec": e.codec, "codec_status": e.codec_status, "params": e.params,
         "image_mode": e.image_mode, "image_info": e.image_info, "compress": e.compress, "manifest": e.manifest,
         "stats": e.stats, "constraints": e.constraints, "encode_ms": e.encode_ms, "label": L,
         "created_at": e.created_at.isoformat()}
    if sample:
        d["sample_oligos"] = runs.read_fasta(e.sequences.fasta_gz)[:sample]
    return d


def ser_sim(s: M.SimulationRun) -> dict:
    return {"id": s.id, "encoding_run_id": s.encoding_run_id, "params": s.params, "totals": s.totals,
            "diffs": s.diffs, "per_oligo_sample": s.per_oligo_sample, "sim_ms": s.sim_ms, "label": L}


def ser_ret(r: M.RetrievalRun, db: Session | None = None) -> dict:
    d = {"id": r.id, "simulation_run_id": r.simulation_run_id, "encoding_run_id": r.encoding_run_id,
         "file_id": r.file_id, "codec": r.codec, "consensus": r.consensus, "exact_match": r.exact_match,
         "sha256_expected": r.sha256_expected, "sha256_got": r.sha256_got, "metrics": r.metrics,
         "decode_report": r.decode_report, "cluster_stats": r.cluster_stats, "image_metrics": r.image_metrics,
         "llm_readiness": r.llm_readiness, "notes": r.notes, "downloadable": bool(r.recovered_path), "label": L,
         "created_at": r.created_at.isoformat()}
    if db is not None:
        sim = db.get(M.SimulationRun, r.simulation_run_id)
        enc = db.get(M.EncodingRun, r.encoding_run_id)
        d["channel"] = sim.params if sim else {}
        d["encoding"] = {"params": enc.params, "stats": enc.stats, "image_mode": enc.image_mode} if enc else {}
    return d


# --------------------------------------------------------------------------- meta

@router.get("/health")
def health() -> dict:
    s = get_settings()
    return {"status": "ok", "version": __version__, "core_ok": bool(list_codecs()), "label": L,
            "database": s.database_url.split(":")[0], "vector_store": "qdrant-server" if s.qdrant_url else "qdrant-local",
            "codecs": list_codecs()}


@router.get("/stats")
def stats(db: Session = Depends(get_db)) -> dict:
    """Counts of real runs in this installation (used on the home page; never invented)."""
    from sqlalchemy import func
    rr = db.scalars(select(M.RetrievalRun)).all()
    return {"files": db.scalar(select(func.count(M.File.id))) or 0,
            "encodings": db.scalar(select(func.count(M.EncodingRun.id))) or 0,
            "retrievals": len(rr), "exact_retrievals": sum(r.exact_match for r in rr),
            "benchmarks": db.scalar(select(func.count(M.Benchmark.id))) or 0,
            "benchmark_runs": db.scalar(select(func.sum(M.Benchmark.n_runs))) or 0,
            "kb_documents": db.scalar(select(func.count(M.KBDocument.id))) or 0,
            "runnable_codecs": len(runnable_codecs()), "research_sources": len(research()["codecs"]),
            "label": L}


@router.get("/benchmark/latest/{file_id}")
def benchmark_latest(file_id: int, db: Session = Depends(get_db)) -> dict:
    b = runs.latest_benchmark(db, file_id)
    if b is None:
        raise HTTPException(404, "no benchmark for this file yet")
    return {"label": L, "id": b.id, "n_runs": b.n_runs, "summary": b.summary, "config": b.config}


@router.get("/benchmark/latest")
def benchmark_latest_any(db: Session = Depends(get_db)) -> dict:
    b = db.scalars(select(M.Benchmark).order_by(M.Benchmark.id.desc())).first()
    if b is None:
        raise HTTPException(404, "no benchmark yet")
    f = db.get(M.File, b.file_id)
    return {"label": L, "id": b.id, "n_runs": b.n_runs, "summary": b.summary, "config": b.config,
            "file": ser_file(f) if f else None}


@router.get("/retrievals")
def retrievals(file_id: int | None = None, db: Session = Depends(get_db)) -> list[dict]:
    q = select(M.RetrievalRun).order_by(M.RetrievalRun.id.desc())
    if file_id is not None:
        q = q.where(M.RetrievalRun.file_id == file_id)
    return [ser_ret(r, db) for r in db.scalars(q.limit(100)).all()]


@router.get("/codecs")
def codecs() -> list[dict]:
    return list_codecs()


@router.get("/research")
def get_research() -> dict:
    return research()


@router.get("/settings")
def settings_view() -> dict:
    s = get_settings()
    llm = get_llm()
    emb = get_embedder()
    return {"llm_provider": llm.name, "llm_is_model": llm.is_llm, "embedding": emb.name, "embedding_dim": emb.dim,
            "anthropic_key_set": bool(s.anthropic_api_key), "anthropic_model": s.anthropic_model,
            "gemini_key_set": bool(s.gemini_api_key), "gemini_model": s.gemini_model,
            "ollama_url": s.ollama_url, "vector_store": s.qdrant_url or "embedded (local path)",
            "database": s.database_url.split("://")[0], "max_upload_mb": s.max_upload_mb,
            "ocr_available": imaging.ocr_available(), "profiles": PROFILES,
            "channel_presets": research()["channel_presets"]}


# --------------------------------------------------------------------------- files

@router.post("/files/upload")
async def upload(file: UploadFile = File(...), db: Session = Depends(get_db)) -> dict:
    limit = int(get_settings().max_upload_mb * 1024 * 1024) + 1
    data = await file.read(limit + 1)
    return ser_file(runs.save_upload(db, file.filename or "upload", data))


@router.get("/files")
def files(db: Session = Depends(get_db)) -> list[dict]:
    return [ser_file(f) for f in db.scalars(select(M.File).order_by(M.File.id.desc())).all()]


@router.get("/files/{file_id}")
def get_file(file_id: int, db: Session = Depends(get_db)) -> dict:
    f = runs._get(db, M.File, file_id)
    d = ser_file(f)
    d["encodings"] = [ser_enc(e) for e in f.encodings]
    return d


@router.get("/files/{file_id}/preview")
def file_preview(file_id: int, db: Session = Depends(get_db)):
    f = runs._get(db, M.File, file_id)
    if f.kind == "image":
        return FileResponse(f.storage_path, media_type=f.mime)
    data = runs.file_bytes(f)
    if f.mime.startswith("text/") or f.mime == "application/json":
        return PlainTextResponse(data[:20000].decode("utf-8", errors="replace"))
    from app.kb.extract import extract_pages
    return PlainTextResponse(" ".join(t for _, t in extract_pages(data, f.mime, f.filename))[:20000])


# --------------------------------------------------------------------------- encode / validate

class EncodeIn(BaseModel):
    file_id: int
    codec: str
    rs_parity_pct: float | None = Field(None, ge=0, le=300)
    payload_bytes: int | None = Field(None, ge=8, le=128)
    overhead: float | None = Field(None, ge=0.05, le=3)
    segment_bytes: int | None = Field(None, ge=8, le=128)
    primers: bool | None = None
    compress: bool = False
    image_mode: str | None = None
    max_side: int = Field(128, ge=16, le=512)


def _codec_params(body) -> dict:
    cls = codec_class(body.codec)
    p = {}
    if getattr(cls, "supports_rs", False):
        p.update({k: getattr(body, k) for k in ("rs_parity_pct", "payload_bytes", "primers") if getattr(body, k) is not None})
    if body.codec == "fountain":
        p.update({k: getattr(body, k) for k in ("overhead", "segment_bytes") if getattr(body, k) is not None})
    return p


@router.post("/encoding/run")
def encoding_run(body: EncodeIn, db: Session = Depends(get_db)) -> dict:
    try:
        codec_class(body.codec)
    except KeyError:
        raise HTTPException(400, f"unknown codec {body.codec!r}") from None
    if body.image_mode and body.image_mode not in imaging.MODES:
        raise HTTPException(400, f"image_mode must be one of {imaging.MODES}")
    e = runs.encode(db, body.file_id, body.codec, _codec_params(body), body.compress, body.image_mode, body.max_side)
    return ser_enc(e, sample=12)


@router.get("/encoding/{run_id}")
def get_encoding(run_id: int, db: Session = Depends(get_db)) -> dict:
    return ser_enc(runs._get(db, M.EncodingRun, run_id), sample=40)


@router.get("/encoding/{run_id}/fasta")
def encoding_fasta(run_id: int, db: Session = Depends(get_db)):
    e = runs._get(db, M.EncodingRun, run_id)
    import gzip
    return Response(gzip.decompress(e.sequences.fasta_gz), media_type="text/plain",
                    headers={"Content-Disposition": f'attachment; filename="dna_twin_enc{run_id}_{e.codec}.fasta"'})


class ValidateIn(BaseModel):
    encoding_run_id: int
    thresholds: dict | None = None


@router.post("/validation/run")
def validation_run(body: ValidateIn, db: Session = Depends(get_db)) -> dict:
    try:
        return {"label": L, **runs.validate(db, body.encoding_run_id, body.thresholds)}
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, f"bad thresholds: {exc}") from exc


# --------------------------------------------------------------------------- simulate / retrieve

class ChannelIn(BaseModel):
    encoding_run_id: int
    sub: float = Field(0.0, ge=0, le=0.5)
    ins: float = Field(0.0, ge=0, le=0.5)
    dele: float = Field(0.0, ge=0, le=0.5)
    dropout: float = Field(0.0, ge=0, le=1)
    years: float = Field(0.0, ge=0, le=100000)
    half_life_years: float = Field(500.0, gt=0)
    copies: int = Field(5, ge=1, le=50)
    copy_dist: str = "fixed"
    seed: int = 42

    def params(self) -> ChannelParams:
        return ChannelParams(**self.model_dump(exclude={"encoding_run_id"}))


@router.post("/simulation/run")
def simulation_run(body: ChannelIn, db: Session = Depends(get_db)) -> dict:
    try:
        p = body.params()
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return ser_sim(runs.simulate(db, body.encoding_run_id, p))


@router.get("/simulation/{sim_id}")
def get_simulation(sim_id: int, db: Session = Depends(get_db)) -> dict:
    return ser_sim(runs._get(db, M.SimulationRun, sim_id))


class RetrieveIn(BaseModel):
    simulation_run_id: int
    consensus: str = "alignment"


@router.post("/retrieval/run")
def retrieval_run(body: RetrieveIn, db: Session = Depends(get_db)) -> dict:
    if body.consensus not in ("alignment", "majority"):
        raise HTTPException(400, "consensus must be 'alignment' or 'majority'")
    return ser_ret(runs.retrieve_run(db, body.simulation_run_id, body.consensus), db)


@router.get("/retrieval/{run_id}")
def get_retrieval(run_id: int, db: Session = Depends(get_db)) -> dict:
    return ser_ret(runs._get(db, M.RetrievalRun, run_id), db)


@router.get("/retrieval/{run_id}/download")
def download(run_id: int, db: Session = Depends(get_db)):
    r = runs._get(db, M.RetrievalRun, run_id)
    if not r.recovered_path:
        raise HTTPException(404, "nothing was recovered in this run")
    f = db.get(M.File, r.file_id)
    p = pathlib.Path(r.recovered_path)
    name = f"recovered_{'exact' if r.exact_match else 'DAMAGED'}_{r.codec}_{f.filename if f.kind != 'image' else pathlib.Path(f.filename).stem + '.png'}"
    return FileResponse(p, filename=name, media_type="image/png" if f.kind == "image" else f.mime)


@router.get("/retrieval/{run_id}/image/{which}")
def retrieval_image(run_id: int, which: str, db: Session = Depends(get_db)):
    if which not in ("ref", "img", "conceal", "diff"):
        raise HTTPException(400, "which must be ref|img|conceal|diff")
    runs._get(db, M.RetrievalRun, run_id)
    p = get_settings().data_dir / "recovered" / f"{which}_{run_id}.png"
    if not p.exists():
        raise HTTPException(404, "no image for this run")
    return FileResponse(p, media_type="image/png")


class QuickIn(BaseModel):
    file_id: int
    codec: str
    rs_parity_pct: float | None = Field(None, ge=0, le=300)
    payload_bytes: int | None = None
    overhead: float | None = None
    segment_bytes: int | None = None
    primers: bool | None = None
    image_mode: str | None = None
    sub: float = Field(0.0, ge=0, le=0.5)
    ins: float = Field(0.0, ge=0, le=0.5)
    dele: float = Field(0.0, ge=0, le=0.5)
    dropout: float = Field(0.0, ge=0, le=1)
    years: float = 0.0
    half_life_years: float = 500.0
    copies: int = Field(5, ge=1, le=50)
    seed: int = 42
    consensus: str = "alignment"


@router.post("/pipeline/run")
def pipeline_run(body: QuickIn, db: Session = Depends(get_db)) -> dict:
    """Encode -> simulate -> retrieve in one call (Digital Twin page)."""
    ch = ChannelParams(sub=body.sub, ins=body.ins, dele=body.dele, dropout=body.dropout, years=body.years,
                       half_life_years=body.half_life_years, copies=body.copies, seed=body.seed)
    e = runs.encode(db, body.file_id, body.codec, _codec_params(body), image_mode=body.image_mode)
    s = runs.simulate(db, e.id, ch)
    r = runs.retrieve_run(db, s.id, body.consensus)
    return {"label": L, "encoding": ser_enc(e, sample=6), "simulation": ser_sim(s), "retrieval": ser_ret(r, db)}


# --------------------------------------------------------------------------- compare / benchmark

@router.get("/comparison/{file_id}")
def comparison(file_id: int, db: Session = Depends(get_db)) -> dict:
    f = runs._get(db, M.File, file_id)
    rr = db.scalars(select(M.RetrievalRun).where(M.RetrievalRun.file_id == f.id).order_by(M.RetrievalRun.id.desc())).all()
    b = runs.latest_benchmark(db, f.id)
    return {"label": L, "file": ser_file(f), "retrievals": [ser_ret(r, db) for r in rr],
            "benchmark": {"id": b.id, "config": b.config, "summary": b.summary, "n_runs": b.n_runs} if b else None}


class BenchIn(BaseModel):
    file_id: int
    codecs: list[str] | None = None
    error_rates: list[float] = Field(default_factory=lambda: [0.0, 0.005, 0.01, 0.02, 0.03, 0.05])
    rs_levels: list[float] = Field(default_factory=lambda: [0.0, 30.0])
    seeds: int = Field(2, ge=1, le=10)
    copies: int = Field(5, ge=1, le=30)
    dropout: float = Field(0.02, ge=0, le=0.9)


@router.post("/benchmark/run")
def benchmark_run(body: BenchIn, db: Session = Depends(get_db)) -> dict:
    if len(body.error_rates) > 12 or any(not 0 <= r <= 0.5 for r in body.error_rates):
        raise HTTPException(400, "error_rates: up to 12 values in [0, 0.5]")
    cfg = SweepConfig(codecs=body.codecs or runnable_codecs(), error_rates=sorted(set(body.error_rates)),
                      rs_levels=body.rs_levels, seeds=list(range(1, body.seeds + 1)), copies=body.copies,
                      dropout=body.dropout)
    b = runs.benchmark(db, body.file_id, cfg)
    return {"label": L, "id": b.id, "n_runs": b.n_runs, "summary": b.summary, "config": b.config}


@router.get("/benchmark/{bench_id}/csv")
def benchmark_csv(bench_id: int, db: Session = Depends(get_db)):
    b = runs._get(db, M.Benchmark, bench_id)
    return FileResponse(b.csv_path, filename=f"dna_twin_benchmark_{bench_id}.csv", media_type="text/csv")


# --------------------------------------------------------------------------- recommendation / report

class RecIn(BaseModel):
    file_id: int
    profile: str = "balanced"
    weights: dict[str, float] | None = None


@router.post("/recommendation/run")
def recommendation_run(body: RecIn, db: Session = Depends(get_db)) -> dict:
    if body.profile not in PROFILES and not body.weights:
        raise HTTPException(400, f"profile must be one of {sorted(PROFILES)} or give weights")
    b = runs.latest_benchmark(db, body.file_id)
    if b is None:
        runs._get(db, M.File, body.file_id)
        b = runs.benchmark(db, body.file_id, SweepConfig(codecs=runnable_codecs(), error_rates=[0.0, 0.01, 0.02, 0.03, 0.05],
                                                          rs_levels=[0.0, 30.0], seeds=[1, 2], copies=5))
    res = recommend(b.summary, body.profile, body.weights)
    db.add(M.Recommendation(file_id=body.file_id, benchmark_id=b.id, profile=body.profile, weights=res.get("weights", {}),
                            ranking=res["ranking"]))
    db.commit()
    return {**res, "benchmark_id": b.id}


@router.get("/recommendation/dataset.csv")
def recommendation_dataset(db: Session = Depends(get_db)):
    bs = db.scalars(select(M.Benchmark)).all()
    return Response(dataset_csv([b.summary for b in bs]), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="dna_twin_simulated_dataset.csv"'})


class ReportIn(BaseModel):
    file_id: int
    profile: str = "balanced"


@router.post("/reports/generate")
def report(body: ReportIn, db: Session = Depends(get_db)):
    f = runs._get(db, M.File, body.file_id)
    b = runs.latest_benchmark(db, f.id)
    rec = recommend(b.summary, body.profile) if b else None
    rr = db.scalars(select(M.RetrievalRun).where(M.RetrievalRun.file_id == f.id).order_by(M.RetrievalRun.id.desc())).all()
    pdf = benchmark_pdf(ser_file(f), b.summary if b else [], rec, [ser_ret(r, db) for r in rr])
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="dna_twin_report_{pathlib.Path(f.filename).stem}.pdf"'})


# --------------------------------------------------------------------------- knowledge base

class IngestIn(BaseModel):
    retrieval_run_id: int


@router.post("/kb/ingest")
def kb_ingest(body: IngestIn, db: Session = Depends(get_db)) -> dict:
    d = rag.ingest(db, body.retrieval_run_id)
    return {"label": L, "doc_id": d.id, "codec": d.codec, "chunks": d.n_chunks, "recovered_exact": d.recovered_exact,
            "embedding": d.embedding}


@router.get("/kb/documents")
def kb_documents(db: Session = Depends(get_db)) -> list[dict]:
    return [{"doc_id": d.id, "file_id": d.file_id, "retrieval_run_id": d.retrieval_run_id, "codec": d.codec,
             "source_file": d.source_file, "recovered_exact": d.recovered_exact, "chunks": d.n_chunks,
             "embedding": d.embedding} for d in db.scalars(select(M.KBDocument).order_by(M.KBDocument.id.desc())).all()]


class QueryIn(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    doc_ids: list[int] | None = None
    file_id: int | None = None
    codec: str | None = None
    top_k: int = Field(5, ge=1, le=20)


@router.post("/kb/query")
def kb_query(body: QueryIn, db: Session = Depends(get_db)) -> dict:
    lazy = None
    doc_ids = body.doc_ids
    if body.file_id is not None and body.codec:
        if body.codec not in runnable_codecs():
            raise HTTPException(400, f"codec {body.codec!r} cannot be run")
        doc, lazy = rag.lazy_document(db, body.file_id, body.codec)
        doc_ids = [doc.id]
    res = rag.query(db, body.question, doc_ids, body.top_k)
    return {**res, "lazy_retrieval": lazy}


class KBCompareIn(BaseModel):
    file_id: int
    question: str = Field(..., min_length=1, max_length=2000)
    codecs: list[str] | None = None
    preset: str | None = None  # name of a channel preset from /research, applied to every codec


@router.post("/kb/compare")
def kb_compare(body: KBCompareIn, db: Session = Depends(get_db)) -> dict:
    codecs_ = body.codecs or runnable_codecs()
    bad = [c for c in codecs_ if c not in runnable_codecs()]
    if bad:
        raise HTTPException(400, f"not runnable: {bad}")
    channel = None
    if body.preset:
        pr = next((p for p in research()["channel_presets"] if p["name"] == body.preset), None)
        if pr is None:
            raise HTTPException(400, f"unknown preset {body.preset!r}")
        channel = {"sub": pr["sub"], "ins": pr["ins"], "dele": pr["del"], "copies": 3, "dropout": 0.02, "seed": 7}
    return rag.compare(db, body.file_id, body.question, codecs_, channel=channel)
