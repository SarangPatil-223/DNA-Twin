# Architecture

## Layers

| Layer | Location | Depends on |
|---|---|---|
| Core simulation | `backend/app/core` | numpy, reedsolo, rapidfuzz, Pillow, scikit-image |
| Services | `backend/app/services/runs.py` | core, SQLAlchemy |
| Knowledge base | `backend/app/kb` | services, Qdrant, LLM/embedding providers |
| Recommendation, reports | `backend/app/recommend.py`, `reports.py` | benchmark summaries |
| HTTP API | `backend/app/api/routes.py` | all of the above |
| UI | `frontend/` (React 19 JSX + Vite + React Router) | HTTP API via `/api/*` proxy (Vite in dev, nginx in Docker) |

The core never imports FastAPI, SQLAlchemy or Qdrant (`tests/core/test_oligo_codec.py` fails the build if it does).

## Data flow for one run

1. **Upload** — type, magic bytes, UTF-8 and size are checked; the file is stored under a hash name.
2. **Container** — `binary.pack_container` adds filename, MIME, size, SHA-256, codec id, version and a header CRC.
3. **Encode** — the codec turns container bytes into oligos and a *manifest* (units, data length, ECC settings). The manifest is the out-of-band catalogue a real archive keeps.
4. **Channel** — `channel.simulate` applies decay, dropout, copy number and per-base sub/ins/del with a seed. The decoder never sees which oligo a read came from.
5. **Retrieve** — reads are clustered by end-keys (Levenshtein), merged into consensus (majority or alignment), mapped back to bytes, checked (CRC16 / parity trit = detection), repaired (Reed-Solomon, 4x voting, GF(2) solving = correction), unpacked and verified with SHA-256.
6. **Metrics** — exact match, byte/bit accuracy (on the pre-decompression container when needed), density, constraints, timings, zero-filled byte ranges.
7. **Knowledge base** — only retrieval output is ingested. Chunks carry `{doc_id, chunk_id, source_file, page, recovered_exact, codec}`. Questions can target one codec (decoded lazily and cached), all documents, or every codec side by side.

## Storage

PostgreSQL (compose) or SQLite (local): `files, encoding_runs, sequences (gzip FASTA), simulation_runs, retrieval_runs, benchmarks, metrics, recommendations, kb_documents, kb_chunks`. Reads and recovered files live on disk under `DATA_DIR`. Alembic migration: `backend/migrations`.
