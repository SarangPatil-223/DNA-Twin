"""Qdrant vector store. Uses QDRANT_URL when set (docker compose), else an embedded local store."""
from __future__ import annotations

import threading

from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from app.settings import get_settings

_lock = threading.Lock()
_client: QdrantClient | None = None


def client() -> QdrantClient:
    global _client
    with _lock:
        if _client is None:
            s = get_settings()
            _client = QdrantClient(url=s.qdrant_url) if s.qdrant_url else QdrantClient(path=str(s.data_dir / "qdrant"))
        return _client


def reset_client() -> None:
    global _client
    with _lock:
        if _client is not None:
            try:
                _client.close()
            except Exception:
                pass
        _client = None


def collection_name(embedder_name: str, dim: int) -> str:
    safe = "".join(ch if ch.isalnum() else "_" for ch in embedder_name)
    return f"dna_twin_{safe}_{dim}"


def ensure(name: str, dim: int) -> None:
    c = client()
    if not c.collection_exists(name):
        c.create_collection(name, vectors_config=qm.VectorParams(size=dim, distance=qm.Distance.COSINE))


def upsert(name: str, ids: list[str], vectors, payloads: list[dict]) -> None:
    client().upsert(name, points=[qm.PointStruct(id=i, vector=v.tolist(), payload=p)
                                  for i, v, p in zip(ids, vectors, payloads)])


def delete_doc(name: str, doc_id: int) -> None:
    c = client()
    if c.collection_exists(name):
        c.delete(name, points_selector=qm.FilterSelector(filter=qm.Filter(must=[
            qm.FieldCondition(key="doc_id", match=qm.MatchValue(value=doc_id))])))


def search(name: str, vector, limit: int = 5, doc_ids: list[int] | None = None) -> list[dict]:
    c = client()
    if not c.collection_exists(name):
        return []
    flt = None
    if doc_ids is not None:
        flt = qm.Filter(must=[qm.FieldCondition(key="doc_id", match=qm.MatchAny(any=doc_ids))])
    res = c.query_points(name, query=vector.tolist(), limit=limit, query_filter=flt, with_payload=True)
    return [{"score": float(p.score), **(p.payload or {})} for p in res.points]
