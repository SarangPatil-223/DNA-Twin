"""Service layer: runs the core pipeline and persists every stage. API routes stay thin."""
from __future__ import annotations

import gzip
import json
import mimetypes
import pathlib

import numpy as np
from fastapi import HTTPException
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import SIMULATION_LABEL, imaging
from app.core.benchmark import SweepConfig, run_sweep, to_csv
from app.core.binary import read_header, sanitize_filename, sha256_hex, unpack_container
from app.core.channel import ChannelParams
from app.core.codec_base import Manifest, codec_class, get_codec, runnable_codecs
from app.core.constraints import ConstraintThresholds, check_batch
from app.core.pipeline import encode_file, retrieve, run_channel
from app.db import models as M
from app.kb.readiness import llm_readiness, readiness_extra
from app.settings import get_settings

ALLOWED = {
    ".txt": "text/plain", ".csv": "text/csv", ".md": "text/markdown", ".json": "application/json",
    ".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
MAGIC = {".pdf": [b"%PDF"], ".png": [b"\x89PNG\r\n\x1a\n"], ".jpg": [b"\xff\xd8\xff"], ".jpeg": [b"\xff\xd8\xff"],
         ".docx": [b"PK\x03\x04"]}


def _dir(sub: str) -> pathlib.Path:
    return get_settings().data_dir / sub


def _get(db: Session, model, id_: int):
    obj = db.get(model, id_)
    if obj is None:
        raise HTTPException(404, f"{model.__tablename__[:-1].replace('_', ' ')} {id_} not found")
    return obj


# --------------------------------------------------------------------------- upload

def save_upload(db: Session, filename: str, data: bytes) -> M.File:
    s = get_settings()
    name = sanitize_filename(filename)
    ext = pathlib.Path(name).suffix.lower()
    if ext not in ALLOWED:
        raise HTTPException(415, f"file type {ext or '(none)'} not allowed; allowed: {sorted(ALLOWED)}")
    if len(data) == 0:
        raise HTTPException(400, "file is empty")
    if len(data) > s.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"file is {len(data) / 1e6:.2f} MB; limit is {s.max_upload_mb} MB "
                                 "(simulating large files at base level is slow)")
    if ext in MAGIC and not any(data.startswith(m) for m in MAGIC[ext]):
        raise HTTPException(415, f"content does not look like a {ext} file")
    if ext in (".txt", ".csv", ".md", ".json"):
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(415, "text files must be UTF-8") from None
    digest = sha256_hex(data)
    path = _dir("uploads") / f"{digest[:16]}{ext}"  # stored under a hash name; never executed
    path.write_bytes(data)
    f = M.File(filename=name, mime=ALLOWED[ext], size=len(data), sha256=digest, storage_path=str(path),
               kind="image" if ALLOWED[ext].startswith("image/") else "document")
    db.add(f)
    db.commit()
    db.refresh(f)
    return f


def file_bytes(f: M.File) -> bytes:
    return pathlib.Path(f.storage_path).read_bytes()


# --------------------------------------------------------------------------- encode

def _fasta(oligos) -> bytes:
    return gzip.compress("".join(f">oligo_{o.index}\n{o.sequence}\n" for o in oligos).encode())


def read_fasta(blob: bytes) -> list[str]:
    return [line for line in gzip.decompress(blob).decode().splitlines() if line and not line.startswith(">")]


def encode(db: Session, file_id: int, codec: str, params: dict | None = None, compress: bool = False,
           image_mode: str | None = None, max_side: int = 128) -> M.EncodingRun:
    f = _get(db, M.File, file_id)
    if codec not in runnable_codecs():
        cls = None
        try:
            cls = codec_class(codec)
        except KeyError:
            pass
        if cls is None:
            raise HTTPException(400, f"unknown codec {codec!r}")
        raise HTTPException(400, f"{cls.label} is future work in this platform and cannot be run")
    data = file_bytes(f)
    info = None
    payload = data
    if f.kind == "image":
        image_mode = image_mode or "pixels"
        try:
            payload, info = imaging.prepare(data, image_mode, max_side)
        except Exception as exc:
            raise HTTPException(400, f"could not read image: {exc}") from exc
    params = {k: v for k, v in (params or {}).items() if v is not None}
    try:
        enc = encode_file(payload, f.filename, f.mime, codec, params, compress)
    except (ValueError, RuntimeError, TypeError) as exc:
        raise HTTPException(400, f"encoding failed: {exc}") from exc
    cpath = _dir("containers") / f"{f.sha256[:12]}_{codec}_{abs(hash(json.dumps(params, sort_keys=True))) % 10**8}.bin"
    cpath.write_bytes(enc.container)
    run = M.EncodingRun(file_id=f.id, codec=codec, codec_status=codec_class(codec).status.value, params=params,
                        image_mode=image_mode if f.kind == "image" else None, image_info=info, compress=compress,
                        manifest=enc.manifest.to_dict(), stats=enc.stats, constraints=enc.constraints,
                        container_path=str(cpath), encode_ms=enc.encode_ms)
    run.sequences = M.SequenceBlob(n_oligos=len(enc.oligos), fasta_gz=_fasta(enc.oligos))
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def encoded_payload(f: M.File, run: M.EncodingRun) -> bytes:
    """The exact bytes that were encoded (raw pixels for image pixel modes), read back from the
    stored container so it always matches what went into DNA."""
    return unpack_container(pathlib.Path(run.container_path).read_bytes()).data


def sequences(db: Session, run_id: int) -> list[str]:
    run = _get(db, M.EncodingRun, run_id)
    return read_fasta(run.sequences.fasta_gz)


def validate(db: Session, run_id: int, thresholds: dict | None) -> dict:
    run = _get(db, M.EncodingRun, run_id)
    t = ConstraintThresholds(**{k: tuple(v) if isinstance(v, list) else v for k, v in (thresholds or {}).items()})
    seqs = read_fasta(run.sequences.fasta_gz)
    f_len, r_len = get_codec(run.codec, **run.params).primer_lengths()
    rep = check_batch([s[f_len : len(s) - r_len if r_len else None] for s in seqs], t)
    return rep.to_dict()


# --------------------------------------------------------------------------- simulate

def simulate(db: Session, encoding_run_id: int, p: ChannelParams) -> M.SimulationRun:
    run = _get(db, M.EncodingRun, encoding_run_id)
    seqs = read_fasta(run.sequences.fasta_gz)
    res, ms = run_channel(seqs, p)
    path = _dir("reads") / f"enc{run.id}_seed{p.seed}_{abs(hash(json.dumps(p.to_dict(), sort_keys=True))) % 10**8}.jsonl.gz"
    path.write_bytes(gzip.compress("\n".join(res.reads).encode()))
    sim = M.SimulationRun(encoding_run_id=run.id, params=p.to_dict(), seed=p.seed, totals=res.totals,
                          diffs=res.diffs, per_oligo_sample=res.per_oligo[:300], reads_path=str(path), sim_ms=ms)
    db.add(sim)
    db.commit()
    db.refresh(sim)
    return sim


def read_reads(sim: M.SimulationRun) -> list[str]:
    raw = gzip.decompress(pathlib.Path(sim.reads_path).read_bytes()).decode()
    return raw.split("\n") if raw else []


# --------------------------------------------------------------------------- retrieve

def _save_png(arr: np.ndarray | None, name: str) -> str | None:
    if arr is None:
        return None
    path = _dir("recovered") / name
    Image.fromarray(arr).save(path, format="PNG")
    return str(path)


def retrieve_run(db: Session, simulation_run_id: int, consensus: str = "alignment") -> M.RetrievalRun:
    sim = _get(db, M.SimulationRun, simulation_run_id)
    run = _get(db, M.EncodingRun, sim.encoding_run_id)
    f = _get(db, M.File, run.file_id)
    payload = encoded_payload(f, run)
    container = pathlib.Path(run.container_path).read_bytes()
    reads = read_reads(sim)
    seqs = read_fasta(run.sequences.fasta_gz)
    ret = retrieve(run.codec, run.params, Manifest.from_dict(run.manifest), reads, container, payload, consensus,
                   float(sim.params["sub"] + sim.params["ins"] + sim.params["dele"]), len(seqs[0]) if seqs else None)

    out = M.RetrievalRun(simulation_run_id=sim.id, encoding_run_id=run.id, file_id=f.id, codec=run.codec,
                         consensus=consensus, exact_match=ret.exact_match, sha256_expected=ret.sha256_expected,
                         sha256_got=ret.sha256_got, metrics=ret.metrics, decode_report=ret.decode_report,
                         cluster_stats=ret.cluster_stats, notes=ret.notes, lost_ranges=[list(r) for r in ret.lost_ranges])
    db.add(out)
    db.flush()

    recovered_bytes = ret.recovered_file
    if f.kind == "image" and run.image_info:
        info = run.image_info
        ref = imaging.reference_pixels(file_bytes(f), info)
        got, how = imaging.reconstruct(recovered_bytes, info)
        q = imaging.quality(ref, got)
        hdr_len = read_header(container)[1]
        mask = imaging.lost_pixel_mask(info, ret.lost_ranges, hdr_len) if got is not None else None
        concealed = imaging.conceal(got, mask) if got is not None else None
        qc = imaging.quality(ref, concealed)
        out.image_metrics = {"mode": info["mode"], "reconstruction": how, "raw": q, "concealed": qc,
                             "lost_pixel_share": float(mask.mean()) if mask is not None else None,
                             "width": info["width"], "height": info["height"]}
        _save_png(ref, f"ref_{out.id}.png")
        _save_png(got, f"img_{out.id}.png")
        _save_png(concealed, f"conceal_{out.id}.png")
        _save_png(imaging.diff_heatmap(ref, got), f"diff_{out.id}.png")
        # the recovered artefact for download is a PNG built from the recovered pixels
        if got is not None:
            path = _save_png(concealed if concealed is not None else got, f"recovered_{out.id}.png")
            out.recovered_path = path
        text_src = concealed if concealed is not None else got
        ocr_text = imaging.ocr(text_src) if text_src is not None else ""
        ref_text = imaging.ocr(ref)
        if ref_text:
            from rapidfuzz.distance import Levenshtein
            out.llm_readiness = {"extractable": True, "source": "OCR of the image",
                                 "text_similarity": round(1 - Levenshtein.normalized_distance(ref_text, ocr_text), 4),
                                 "readiness": round(100 * (1 - Levenshtein.normalized_distance(ref_text, ocr_text)), 1),
                                 "ocr_chars": len(ocr_text)}
        else:
            out.llm_readiness = {"extractable": False, "readiness": None,
                                 "reason": "OCR found no text in the original image" if imaging.ocr_available() else "OCR (tesseract) not installed"}
    else:
        if recovered_bytes is not None:
            ext = pathlib.Path(f.filename).suffix
            path = _dir("recovered") / f"recovered_{out.id}{ext}"
            path.write_bytes(recovered_bytes)
            out.recovered_path = str(path)
        out.llm_readiness = llm_readiness(payload, recovered_bytes, f.mime, f.filename)
    for k, v in ret.metrics.items():
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            db.add(M.Metric(run_type="retrieval", run_id=out.id, name=k, value=float(v)))
    db.commit()
    db.refresh(out)
    return out


def full_run(db: Session, file_id: int, codec: str, params: dict | None, channel: ChannelParams,
             consensus: str = "alignment", image_mode: str | None = None) -> M.RetrievalRun:
    enc = encode(db, file_id, codec, params, image_mode=image_mode)
    sim = simulate(db, enc.id, channel)
    return retrieve_run(db, sim.id, consensus)


# --------------------------------------------------------------------------- benchmark

def benchmark(db: Session, file_id: int, cfg: SweepConfig) -> M.Benchmark:
    f = _get(db, M.File, file_id)
    data = file_bytes(f)
    mime = f.mime
    if f.kind == "image":
        data, _ = imaging.prepare(data, "pixels", 96)
    bad = [c for c in cfg.codecs if c not in runnable_codecs()]
    if bad:
        raise HTTPException(400, f"not runnable: {bad}")
    extra = (lambda o, r, m: readiness_extra(o, r, m, f.filename)) if f.kind == "document" else None
    res = run_sweep(data, f.filename, mime, cfg, extra=extra)
    path = _dir("benchmarks") / f"bench_file{f.id}_{len(list(_dir('benchmarks').iterdir()))}.csv"
    path.write_text(to_csv(res["rows"]))
    b = M.Benchmark(file_id=f.id, config={k: list(v) if isinstance(v, tuple) else v for k, v in cfg.__dict__.items()},
                    summary=res["summary"], csv_path=str(path), n_runs=len(res["rows"]))
    db.add(b)
    db.commit()
    db.refresh(b)
    return b


def latest_benchmark(db: Session, file_id: int) -> M.Benchmark | None:
    return db.scalars(select(M.Benchmark).where(M.Benchmark.file_id == file_id).order_by(M.Benchmark.id.desc())).first()


def guess_mime(name: str) -> str:
    return mimetypes.guess_type(name)[0] or "application/octet-stream"


LABEL = SIMULATION_LABEL
