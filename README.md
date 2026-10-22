# DNA Twin

A software digital twin of DNA data storage with an LLM knowledge base on top. It is a **simulation**:
nothing is synthesized or sequenced, and every simulated number is labelled "Simulation Result".

```
file → container (header + SHA-256) → codec → oligos → noisy channel → reads
     → clustering + consensus → CRC (detection) → Reed-Solomon / voting / fountain (correction)
     → byte-exact file (SHA-256) → text → chunks → embeddings → Qdrant → LLM answers with citations
```

## Run it

With Docker: `cp .env.example .env && docker compose up --build`, then open http://localhost:3000.

Without Docker (SQLite + embedded Qdrant, nothing else to install):

```
cd backend && pip install -r requirements.txt && uvicorn app.main:app --port 8000
cd frontend && npm install && npm run dev      # http://localhost:3000, forwards /api to :8000
```

Tests: `cd backend && pytest` (190 tests). Benchmark from the command line:
`python scripts/benchmark.py yourfile.txt --seeds 5 --out results.csv`.

## LLM

Set `GEMINI_API_KEY` (Gemini), `ANTHROPIC_API_KEY` (Claude), or run Ollama. With neither, answers are extractive quotes from the
recovered text, and the UI says so. Embeddings default to an offline hashing embedder; install
`sentence-transformers` for neural embeddings.

## What is where

- `backend/app/core/` pure-Python simulation library (no web or DB imports; a test enforces this)
- `backend/app/services`, `api`, `db`, `kb` persistence, HTTP API, knowledge base
- `frontend/` React UI in plain JSX (Vite, React Router, Tailwind, Recharts)
- `docs/` architecture, algorithms, methodology, API
