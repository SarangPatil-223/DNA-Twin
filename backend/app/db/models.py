"""SQLAlchemy models. Works on PostgreSQL (docker compose) and SQLite (local dev / tests)."""
from __future__ import annotations

import datetime as dt

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class Base(DeclarativeBase):
    type_annotation_map = {dict: JSON, list: JSON}


class File(Base):
    __tablename__ = "files"
    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    mime: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    storage_path: Mapped[str] = mapped_column(String(500))
    kind: Mapped[str] = mapped_column(String(20), default="document")  # document | image
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)
    encodings: Mapped[list["EncodingRun"]] = relationship(back_populates="file", cascade="all, delete-orphan")


class EncodingRun(Base):
    __tablename__ = "encoding_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("files.id"), index=True)
    codec: Mapped[str] = mapped_column(String(40))
    codec_status: Mapped[str] = mapped_column(String(20))
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    image_mode: Mapped[str | None] = mapped_column(String(20), nullable=True)
    image_info: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    compress: Mapped[bool] = mapped_column(Boolean, default=False)
    manifest: Mapped[dict] = mapped_column(JSON)
    stats: Mapped[dict] = mapped_column(JSON)
    constraints: Mapped[dict] = mapped_column(JSON)
    container_path: Mapped[str] = mapped_column(String(500))
    encode_ms: Mapped[float] = mapped_column(Float)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)
    file: Mapped[File] = relationship(back_populates="encodings")
    sequences: Mapped["SequenceBlob"] = relationship(back_populates="encoding", cascade="all, delete-orphan", uselist=False)


class SequenceBlob(Base):
    """Oligos stored as gzip-compressed FASTA."""
    __tablename__ = "sequences"
    id: Mapped[int] = mapped_column(primary_key=True)
    encoding_run_id: Mapped[int] = mapped_column(ForeignKey("encoding_runs.id"), unique=True)
    n_oligos: Mapped[int] = mapped_column(Integer)
    fasta_gz: Mapped[bytes] = mapped_column(LargeBinary)
    encoding: Mapped[EncodingRun] = relationship(back_populates="sequences")


class SimulationRun(Base):
    __tablename__ = "simulation_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    encoding_run_id: Mapped[int] = mapped_column(ForeignKey("encoding_runs.id"), index=True)
    params: Mapped[dict] = mapped_column(JSON)
    seed: Mapped[int] = mapped_column(Integer)
    totals: Mapped[dict] = mapped_column(JSON)
    diffs: Mapped[list] = mapped_column(JSON, default=list)
    per_oligo_sample: Mapped[list] = mapped_column(JSON, default=list)
    reads_path: Mapped[str] = mapped_column(String(500))
    sim_ms: Mapped[float] = mapped_column(Float)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)


class RetrievalRun(Base):
    __tablename__ = "retrieval_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    simulation_run_id: Mapped[int] = mapped_column(ForeignKey("simulation_runs.id"), index=True)
    encoding_run_id: Mapped[int] = mapped_column(ForeignKey("encoding_runs.id"), index=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("files.id"), index=True)
    codec: Mapped[str] = mapped_column(String(40))
    consensus: Mapped[str] = mapped_column(String(20))
    exact_match: Mapped[bool] = mapped_column(Boolean)
    sha256_expected: Mapped[str] = mapped_column(String(64))
    sha256_got: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metrics: Mapped[dict] = mapped_column(JSON)
    decode_report: Mapped[dict] = mapped_column(JSON)
    cluster_stats: Mapped[dict] = mapped_column(JSON)
    image_metrics: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    llm_readiness: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[list] = mapped_column(JSON, default=list)
    lost_ranges: Mapped[list] = mapped_column(JSON, default=list)
    recovered_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)


class Benchmark(Base):
    __tablename__ = "benchmarks"
    id: Mapped[int] = mapped_column(primary_key=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("files.id"), index=True)
    config: Mapped[dict] = mapped_column(JSON)
    summary: Mapped[list] = mapped_column(JSON)
    csv_path: Mapped[str] = mapped_column(String(500))
    n_runs: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)


class Metric(Base):
    """Flat metric log (run_type, run_id, name, value) for ad-hoc analysis."""
    __tablename__ = "metrics"
    id: Mapped[int] = mapped_column(primary_key=True)
    run_type: Mapped[str] = mapped_column(String(20), index=True)
    run_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(60))
    value: Mapped[float | None] = mapped_column(Float, nullable=True)


class Recommendation(Base):
    __tablename__ = "recommendations"
    id: Mapped[int] = mapped_column(primary_key=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("files.id"), index=True)
    benchmark_id: Mapped[int | None] = mapped_column(ForeignKey("benchmarks.id"), nullable=True)
    profile: Mapped[str] = mapped_column(String(30))
    weights: Mapped[dict] = mapped_column(JSON)
    ranking: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)


class KBDocument(Base):
    __tablename__ = "kb_documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    retrieval_run_id: Mapped[int] = mapped_column(ForeignKey("retrieval_runs.id"), unique=True)
    file_id: Mapped[int] = mapped_column(ForeignKey("files.id"), index=True)
    codec: Mapped[str] = mapped_column(String(40))
    source_file: Mapped[str] = mapped_column(String(255))
    recovered_exact: Mapped[bool] = mapped_column(Boolean)
    n_chunks: Mapped[int] = mapped_column(Integer)
    embedding: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=now)


class KBChunk(Base):
    __tablename__ = "kb_chunks"
    id: Mapped[int] = mapped_column(primary_key=True)
    doc_id: Mapped[int] = mapped_column(ForeignKey("kb_documents.id"), index=True)
    chunk_idx: Mapped[int] = mapped_column(Integer)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer)
    qdrant_point_id: Mapped[str] = mapped_column(String(64))
