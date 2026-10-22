# Methodology

## Channel model (simulation, not measured biology)

Per oligo species: survival = (1 − dropout) × 0.5^(years / half-life). Survivors get `copies` reads (fixed or Poisson). Each base of each read independently gets a substitution, deletion or insertion with the configured probabilities. Presets on the Digital Twin page use per-base magnitudes reported by the DT4DDS study (Illumina substitutions ~1.8e-3/nt; electrochemical synthesis ~13.5e-3/nt, deletion-dominated). How the low-fidelity rate is split between insertions and deletions is our assumption. The default benchmark mix is sub:ins:del = 50:10:40, also an assumption.

## Retrieval without ground truth

Clustering uses only the reads: a key made of the first and last 20 nt, exact grouping first, then nearest key within a distance that scales with the assumed error rate (3–8 edits). Consensus is alignment-based by default and can restore bases missing from the reference read.

## Metrics

- **Exact match**: SHA-256 of the recovered file equals the original. This is the headline metric.
- **Byte / bit accuracy**: position-wise on the file; if the recovered header is damaged, the payload is cut using the original header length. With compression on, partial accuracy is only meaningful before decompression.
- **Error tolerance**: highest tested rate at which every seed, and every lower rate, recovered exactly. Never interpolated.
- **LLM readiness (0–100)**: 40 % text similarity (1 − normalised edit distance), 30 % share of original chunks reproduced exactly, 30 % overlap of top-k chunks retrieved for probe queries from the recovered vs the original index. The original is used only as ground truth for this score; it is never ingested.
- **Images**: PSNR and SSIM against the original pixels at the stored resolution; *concealment* fills zero-filled pixels by diffusion from known neighbours, using the decoder's list of lost byte ranges.

## Recommendation

Min-max normalised metrics across the benchmarked variants, weighted by profile (archive, LLM/RAG, cost/density, balanced). Every reason quotes the measured value. Scores are relative to the sweep; fewer than 3 seeds triggers a warning. `ModelScorer` accepts a learned model trained on the exported *Simulated Dataset* CSV; nothing requires one.
