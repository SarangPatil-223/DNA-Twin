# DNA Twin — Implementation Plan

> **Simulation only.** DNA Twin is a software digital twin of DNA data storage. It does not synthesize
> or sequence DNA. Every simulated result is labelled **"Simulation Result"** and no output claims
> biological validation.

## 0. Repo inspection (done before writing this plan)

The repo was empty apart from the reference demo `dna_recovery.html`. The demo shows the right
*flow* (input → encode two ways → mutate at a slider-set rate with a seed → decode → compare →
download), and the UI keeps that flow. Its *code* is not reused, because five parts of it would
produce wrong results in this project:

| # | What the demo does | Why it is wrong for DNA Twin | What DNA Twin does instead |
|---|---|---|---|
| 1 | Its "Church" card is a fixed 2 bits/base map (`00→A … 11→T`). | Church et al. 2012 used **1 bit/base** (A/C = 0, G/T = 1), with the free choice used to avoid homopolymers and balance GC. The demo mislabels a raw quaternary map as Church. | Church codec = 1 bit/base per the spec. A raw 2-bit map is kept only as a clearly labelled "density ceiling" reference, never called Church. |
| 2 | Its Goldman encoder turns the **whole file into one big integer**, then base-3, then rotating bases. No fragments, no index. | One substitution changes every later trit's meaning, so one error can wreck the whole file. The demo's note that Goldman "falls faster" is an artifact of this, not a property of Goldman 2013. | Goldman codec works per fragment (100 nt, 25-nt offset, 4x coverage, index trits, parity trit), as in the paper. |
| 3 | Only substitutions are simulated. | Real channels have insertions, deletions and dropouts; those break positional comparison. | `channel.py` simulates subs / ins / dels / dropout / decay; diffs use alignment (edit distance), not position-by-position. |
| 4 | Accuracy = position-wise byte match. | Meaningless once indels or compression are involved. | Report **exact match (SHA-256)** as the headline; byte/bit accuracy computed on the *pre-decompression container* (see §4). |
| 5 | FNV-1a 32-bit checksum. | Not a cryptographic hash; fine for a demo, not for "byte-exact verified". | SHA-256 in the metadata header and in every retrieval run. |

## Status (30 Sep 2026)

| Phase | Status |
|---|---|
| 1 Core library | done |
| 2 Codecs | Church, raw 2-bit implemented; Goldman, Fountain, Yin-Yang simplified; HEDGES, DNA-Aeon, DP-DNA future work |
| 3 ECC | RS outer code, CRC detection, clustering + majority/alignment consensus |
| 4 Channel | sub/ins/del, dropout, decay, copies, seed, per-oligo stats, diffs |
| 5 Metrics + benchmark | done (API, UI, CLI, CSV) |
| 6 Tests | 190 passing |
| 7 API + DB | done, SQLite or PostgreSQL, Alembic migration |
| 8 Knowledge base | recovered-data-only RAG, lazy decode, cross-codec compare, LLM readiness |
| 9 Recommendation | weighted profiles with measured reasons, dataset export |
| 10 Frontend | React JSX (Vite) with 13 pages, verified in a headless browser |
| 11 Docs + reports | docs/, per-file PDF report, research PDF |
| Added | Image lab: raw-pixel modes, PSNR/SSIM, concealment, OCR |

## 1. Architecture

```
file ─► binary.pack_container (header + optional zlib) ─► outer RS code (Phase 3)
     ─► oligo framing [index | payload | CRC16] ─► Codec: frame bytes ─► nucleotides
     ─► channel (subs/ins/dels/dropout/decay, N copies, seed)
     ─► cluster by index ─► consensus ─► Codec: nucleotides ─► frame bytes
     ─► CRC check (DETECTION: bad frames → erasures) ─► RS decode (CORRECTION)
     ─► binary.unpack_container ─► SHA-256 verify ─► text extraction ─► chunk ─► embed ─► Qdrant ─► LLM
```

Error **detection** (CRC16 per oligo) and error **correction** (RS across oligos, consensus across
copies) live in different modules, are reported in different fields, and are named differently in the UI.

## 2. Folder structure

```
dna-twin/
├── PLAN.md
├── docker-compose.yml               postgres + qdrant + backend + frontend
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── app/
│   │   ├── core/                    PURE PYTHON — no web/DB imports (enforced by a test)
│   │   │   ├── binary.py            container header, bytes↔bits, compression
│   │   │   ├── crc.py               CRC-16/CCITT-FALSE (detection only)
│   │   │   ├── oligo.py             Oligo, OligoLayout, framing/deframing
│   │   │   ├── codec_base.py        abstract Codec + FrameCodec helper + registry
│   │   │   ├── constraints.py       GC, homopolymer, entropy → VALID/WARNING/INVALID
│   │   │   ├── codecs/              church.py, goldman.py, fountain.py, yinyang.py   (Phase 2)
│   │   │   ├── ecc/                 reed_solomon.py, consensus.py                    (Phase 3)
│   │   │   ├── channel.py           noise simulator                                  (Phase 4)
│   │   │   ├── metrics.py           retrieval metrics                                (Phase 5)
│   │   │   └── pipeline.py          end-to-end orchestration                         (Phase 5)
│   │   ├── api/                     FastAPI routers                                  (Phase 7)
│   │   ├── db/                      SQLAlchemy models + Alembic                      (Phase 7)
│   │   ├── kb/                      extraction, chunking, providers, Qdrant          (Phase 8)
│   │   ├── recommend/               rule-based scorer + RF interface                 (Phase 9)
│   │   └── main.py                  FastAPI app (/health from Phase 1)
│   ├── scripts/benchmark.py         codec × error rate × redundancy × seeds → CSV    (Phase 5)
│   └── tests/
├── frontend/                        React + Vite + React Router                      (Phase 10)
└── docs/                            architecture, algorithms, methodology, api       (Phase 11)
```

## 3. Phase list

| Phase | Deliverable | Exit test |
|---|---|---|
| 1 | Core library: container, CRC16, oligo framing, Codec ABC, constraints; `/health` | pytest green; zero-noise frame round-trip on TXT/CSV/PNG/PDF |
| 2 | Church (1 bit/nt), Goldman (fragmented, 4x), DNA Fountain (simplified), Yin-Yang or future_work | Round-trip at zero noise for every codec marked `implemented`/`simplified` |
| 3 | RS outer code (erasure + error), CRC→erasure, N-copy clustering + consensus | RS recovers exactly at designed loss; fails honestly beyond it |
| 4 | Channel: subs/ins/dels/dropout/decay/copies/seed, per-oligo stats, alignment diff | Each error type tested; same seed → identical output |
| 5 | Metrics + benchmark CSV (mean ± std over seeds) | Numbers come only from runs |
| 6 | Full test suite incl. integration upload→compare | All green |
| 7 | FastAPI endpoints + Postgres schema + upload security | API tests via TestClient |
| 8 | RAG over recovered data only | Refuses ingestion of non-retrieved files; warning on non-exact recovery |
| 9 | Weighted, explainable recommender; RF interface optional | Works with no model file |
| 10 | React UI (Vite) | Build passes; every result card badged "Simulation Result" |
| 11 | Docs + PDF report | — |

## 4. Key design decisions

- **Compression vs. accuracy metrics.** A single wrong bit in a zlib stream usually makes the whole
  decompression fail, so "byte accuracy of the recovered file" would read ~0% even when 99.9% of the
  DNA decoded correctly. Compression is optional per run (`compress: bool`, off by default in benchmarks),
  and partial-accuracy metrics are measured on the container bytes before decompression. Exact
  recovery (SHA-256) stays the headline metric.
- **Container is self-delimiting.** The header carries the payload length, so trailing padding from
  fixed-length oligos is discarded without a separate length oligo.
- **Framing is shared, mapping is per codec.** `FrameCodec` handles `[index | payload | CRC16]` at the
  byte level; each codec only defines `frame bytes ↔ nucleotides`. Codecs whose paper layout differs
  (Goldman fragments, Fountain droplets with seeds) override `encode/decode` directly.
- **Missing oligos raise a typed error** (`MissingOligosError` with the indices) until Phase 3 turns
  them into RS erasures. No silent zero-filling.
- **Status honesty.** `status` is `implemented`, `simplified` or `future_work`. A codec is only
  `implemented` if its round-trip tests pass; HEDGES and DP-DNA are `future_work` stubs that raise
  `NotImplementedError`.

## 5. API contracts (Phase 7, draft)

All responses carry `"label": "Simulation Result"` where they contain simulated data.

| Method | Path | Body → Response (abridged) |
|---|---|---|
| GET | /health | → `{status, version, core_ok}` |
| POST | /files/upload | multipart file → `{file_id, filename, mime, size, sha256}` |
| POST | /encoding/run | `{file_id, codec, oligo_len, compress, rs_redundancy_pct}` → `{encoding_run_id, n_oligos, n_nt, density, gc, max_homopolymer, constraint_report, encode_ms}` |
| POST | /validation/run | `{encoding_run_id, thresholds?}` → `{status, violations[], per_oligo_summary}` |
| POST | /simulation/run | `{encoding_run_id, sub, ins, del, dropout, years, copies, seed}` → `{simulation_run_id, totals, per_oligo_stats_ref}` |
| POST | /retrieval/run | `{simulation_run_id, consensus: "majority"\|"alignment"}` → `{retrieval_run_id, exact_match, sha256_expected, sha256_got, byte_acc, bit_acc, crc_failures, rs_corrected, decode_ms}` |
| GET | /comparison/{file_id} | → rows per codec × run |
| POST | /recommendation/run | `{file_id, weights?}` → `{ranking[], reasons[]}` (measured values only) |
| POST | /reports/generate | `{file_id}` → PDF stream |
| POST | /kb/ingest | `{retrieval_run_id}` → `{doc_id, chunks, recovered_exact}` (rejects anything not from retrieval) |
| POST | /kb/query | `{question, top_k}` → `{answer, citations[], warnings[]}` |

## 6. Database schema (Phase 7, draft)

```
files(id PK, filename, mime, size, sha256, storage_path, created_at)
encoding_runs(id PK, file_id FK, codec, codec_status, params JSONB, n_oligos, n_nt, density,
              gc, max_homopolymer, constraint_status, encode_ms, created_at)
sequences(id PK, encoding_run_id FK, blob BYTEA  -- zstd-compressed FASTA, or storage_path)
simulation_runs(id PK, encoding_run_id FK, params JSONB, seed, totals JSONB, reads_ref, sim_ms, created_at)
retrieval_runs(id PK, simulation_run_id FK, exact_match, sha256_got, byte_acc, bit_acc,
               crc_failures, rs_corrected, erasures, decode_ms, recovered_path, created_at)
metrics(id PK, run_type, run_id, name, value, unit)
recommendations(id PK, file_id FK, weights JSONB, ranking JSONB, reasons JSONB, created_at)
kb_documents(id PK, retrieval_run_id FK UNIQUE, file_id FK, codec, recovered_exact, created_at)
kb_chunks(id PK, doc_id FK, chunk_idx, page, text, qdrant_point_id, token_count)
```

## 7. Known risks

- Goldman at 4x coverage and Fountain at realistic overheads make files large; benchmarks use small
  files (≤ 64 KB) by default so sweeps finish in minutes.
- Docker is not available in the build sandbox; compose files are written and linted but first
  run is on the user's machine.
- Python big-int / per-base loops are slow; hot paths use NumPy where it matters.
