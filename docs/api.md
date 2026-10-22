# API

Base URL `http://localhost:8000` (also mounted under `/api`). Responses with simulated data carry `"label": "Simulation Result"`.

| Method | Path | Purpose |
|---|---|---|
| GET | /health, /codecs, /research, /settings, /stats | status, codec list, literature table, providers, run counts |
| POST | /files/upload | multipart upload (txt, csv, md, json, pdf, docx, png, jpg; ≤ 2 MB) |
| GET | /files, /files/{id}, /files/{id}/preview | list, detail, text/image preview |
| POST | /encoding/run | `{file_id, codec, rs_parity_pct?, payload_bytes?, primers?, overhead?, segment_bytes?, compress?, image_mode?, max_side?}` |
| GET | /encoding/{id}, /encoding/{id}/fasta | stats, constraint report, sample oligos; FASTA |
| POST | /validation/run | `{encoding_run_id, thresholds?}` → VALID/WARNING/INVALID with exact violations |
| POST | /simulation/run | `{encoding_run_id, sub, ins, dele, dropout, years, half_life_years, copies, copy_dist, seed}` |
| GET | /simulation/{id} | totals, per-oligo sample, base-level diffs |
| POST | /retrieval/run | `{simulation_run_id, consensus}` → exact match, hashes, detection and correction reports, LLM readiness, image metrics |
| GET | /retrieval/{id}, /retrieval/{id}/download, /retrieval/{id}/image/{ref,img,conceal,diff}, /retrievals?file_id= | results, recovered file, image previews, history |
| POST | /pipeline/run | encode + simulate + retrieve in one call |
| GET | /comparison/{file_id} | all retrievals + latest benchmark |
| POST | /benchmark/run | `{file_id, codecs, error_rates, rs_levels, seeds, copies, dropout}` |
| GET | /benchmark/{id}/csv, /benchmark/latest, /benchmark/latest/{file_id} | CSV and summaries |
| POST | /recommendation/run | `{file_id, profile, weights?}` → ranking with measured reasons |
| GET | /recommendation/dataset.csv | Simulated Dataset for training a learned scorer |
| POST | /reports/generate | `{file_id, profile}` → PDF |
| POST | /kb/ingest | `{retrieval_run_id}` (404 for anything that is not a retrieval run) |
| GET | /kb/documents | ingested documents |
| POST | /kb/query | `{question, doc_ids?}` or `{question, file_id, codec}` (lazy decode + cache) |
| POST | /kb/compare | `{file_id, question, codecs?, preset?}` → one answer per codec |
