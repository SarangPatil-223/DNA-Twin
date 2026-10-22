"""Transparent, rule-based codec recommendation from benchmark results.

score(variant) = sum_i weight_i * normalized_metric_i, metrics min-max normalized across the
variants that were actually benchmarked (so the score is relative to this file and this sweep).
Every reason quotes the measured value it rests on. A learned model can be plugged in through
`ModelScorer`, but nothing requires one.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from typing import Protocol

from app.core import SIMULATION_LABEL

PROFILES: dict[str, dict[str, float]] = {
    "archival": {"recovery": 0.35, "tolerance": 0.25, "byte_accuracy": 0.10, "density": 0.15, "constraints": 0.15},
    "llm_rag": {"recovery": 0.25, "llm_readiness": 0.35, "retrieval_speed": 0.15, "tolerance": 0.15, "constraints": 0.10},
    "cost_density": {"density": 0.45, "recovery": 0.30, "constraints": 0.15, "retrieval_speed": 0.10},
    "balanced": {"recovery": 0.25, "tolerance": 0.15, "density": 0.15, "constraints": 0.15, "llm_readiness": 0.15,
                 "retrieval_speed": 0.15},
}

LABELS = {
    "recovery": "byte-exact recovery rate",
    "tolerance": "error tolerance",
    "byte_accuracy": "mean byte accuracy",
    "density": "density",
    "constraints": "biochemical constraint compliance",
    "llm_readiness": "LLM readiness",
    "retrieval_speed": "retrieval time",
}
_CONSTRAINT = {"VALID": 1.0, "WARNING": 0.5, "INVALID": 0.0}


class ModelScorer(Protocol):
    """Optional learned scorer (e.g. a Random Forest trained on the Simulated Dataset)."""

    def predict_recovery(self, features: dict) -> float: ...


@dataclass
class VariantStats:
    variant: str
    codec: str
    recovery: float
    tolerance: float | None
    byte_accuracy: float
    density: float
    constraints: float
    constraint_status: str
    max_homopolymer: int
    llm_readiness: float | None
    retrieval_ms: float


def aggregate(summary: list[dict]) -> list[VariantStats]:
    by: dict[str, list[dict]] = {}
    for r in summary:
        by.setdefault(r["variant"], []).append(r)
    out = []
    for v, rows in by.items():
        f = rows[0]
        llm = [r.get("llm_readiness_mean") for r in rows if r.get("llm_readiness_mean") is not None]
        out.append(VariantStats(
            variant=v, codec=f["codec"],
            recovery=sum(r["exact_match_mean"] for r in rows) / len(rows),
            tolerance=f.get("error_tolerance"),
            byte_accuracy=sum((r["file_byte_accuracy_mean"] or 0) for r in rows) / len(rows),
            density=f["density_bits_per_nt"],
            constraints=_CONSTRAINT.get(f["constraint_status"], 0) * (1.0 if f["max_homopolymer"] <= 4 else 0.7),
            constraint_status=f["constraint_status"], max_homopolymer=f["max_homopolymer"],
            llm_readiness=(sum(llm) / len(llm)) if llm else None,
            retrieval_ms=sum(r["retrieval_ms_mean"] or 0 for r in rows) / len(rows),
        ))
    return out


def _metric(s: VariantStats, key: str) -> float | None:
    return {
        "recovery": s.recovery, "tolerance": s.tolerance if s.tolerance is not None else -0.01,
        "byte_accuracy": s.byte_accuracy, "density": s.density, "constraints": s.constraints,
        "llm_readiness": s.llm_readiness, "retrieval_speed": -s.retrieval_ms,
    }[key]


def _fmt(s: VariantStats, key: str) -> str:
    if key == "recovery":
        return f"{s.recovery:.0%} of tested conditions recovered byte-exactly"
    if key == "tolerance":
        return "no tested error rate recovered exactly" if s.tolerance is None else f"exact up to {s.tolerance:.1%} error rate"
    if key == "byte_accuracy":
        return f"{s.byte_accuracy:.1%} mean byte accuracy"
    if key == "density":
        return f"{s.density:.3f} bits/nt"
    if key == "constraints":
        return f"constraints {s.constraint_status}, max homopolymer {s.max_homopolymer}"
    if key == "llm_readiness":
        return "LLM readiness not measured (no extractable text)" if s.llm_readiness is None else f"LLM readiness {s.llm_readiness:.0f}/100"
    return f"{s.retrieval_ms:.0f} ms mean retrieval"


def recommend(summary: list[dict], profile: str = "balanced", weights: dict | None = None,
              model: ModelScorer | None = None) -> dict:
    if not summary:
        return {"label": SIMULATION_LABEL, "ranking": [], "headline": "Run a benchmark first."}
    w = dict(weights or PROFILES.get(profile) or PROFILES["balanced"])
    stats = aggregate(summary)
    if all(s.llm_readiness is None for s in stats):
        w.pop("llm_readiness", None)  # cannot weigh what was not measured
    total_w = sum(w.values()) or 1.0
    w = {k: v / total_w for k, v in w.items()}

    norms: dict[str, dict[str, float]] = {}
    for key in w:
        vals = {s.variant: _metric(s, key) for s in stats}
        present = [v for v in vals.values() if v is not None]
        lo, hi = (min(present), max(present)) if present else (0, 0)
        norms[key] = {v: (0.0 if x is None else (1.0 if hi == lo else (x - lo) / (hi - lo))) for v, x in vals.items()}

    ranking = []
    for s in stats:
        contrib = {k: w[k] * norms[k][s.variant] for k in w}
        score = 100 * sum(contrib.values())
        best_keys = sorted(contrib, key=lambda k: -contrib[k])
        reasons = []
        for k in w:
            best_v = max(stats, key=lambda x: norms[k][x.variant])
            tag = "best in sweep" if norms[k][s.variant] == 1.0 else f"best: {best_v.variant}, {_fmt(best_v, k)}"
            reasons.append({"metric": LABELS[k], "weight": round(w[k], 3), "value": _fmt(s, k),
                            "normalized": round(norms[k][s.variant], 3), "points": round(100 * contrib[k], 1),
                            "comparison": tag})
        entry = {"variant": s.variant, "codec": s.codec, "score": round(score, 1), "reasons": reasons,
                 "strengths": [LABELS[k] for k in best_keys[:2] if norms[k][s.variant] > 0.5],
                 "weaknesses": [LABELS[k] for k in w if norms[k][s.variant] < 0.25]}
        if model is not None:
            entry["model_predicted_recovery"] = float(model.predict_recovery(s.__dict__))
        ranking.append(entry)
    ranking.sort(key=lambda e: -e["score"])
    top = ranking[0]
    top_stats = next(s for s in stats if s.variant == top["variant"])
    runner = ranking[1] if len(ranking) > 1 else None
    names = {"archival": "long-term archive", "llm_rag": "LLM / RAG", "cost_density": "cost and density", "balanced": "balanced"}
    headline = (f"For the {names.get(profile, profile)} profile, {top['variant']} scores {top['score']}/100: "
                f"{_fmt(top_stats, 'recovery')}, {_fmt(top_stats, 'tolerance')}, {_fmt(top_stats, 'density')}.")
    if runner:
        headline += f" Runner-up: {runner['variant']} ({runner['score']}/100)."
    seeds = min((r.get("n_seeds", 1) for r in summary), default=1)
    caveat = "Scores are relative to the codecs and error rates in this sweep, on a simulated channel."
    if seeds < 3:
        caveat += f" Only {seeds} seed(s) per condition: rerun the benchmark with 3 or more seeds before relying on the order."
    return {"label": SIMULATION_LABEL, "profile": profile, "weights": w, "ranking": ranking, "headline": headline,
            "caveat": caveat, "seeds_per_condition": seeds}


def dataset_csv(benchmarks: list[list[dict]]) -> str:
    """'Simulated Dataset' for training a learned scorer: one row per variant x condition with a
    binary label (recovered byte-exactly in every seed)."""
    buf = io.StringIO()
    buf.write(f"# Simulated Dataset - {SIMULATION_LABEL}; generated by DNA Twin benchmarks, not wet-lab data\n")
    fields = ["codec", "variant", "rs_parity_pct", "error_rate", "density_bits_per_nt", "gc", "max_homopolymer",
              "constraint_status", "file_byte_accuracy_mean", "retrieval_ms_mean", "label_exact"]
    w = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    for summary in benchmarks:
        for r in summary:
            w.writerow({**r, "label_exact": int(r["exact_match_mean"] == 1.0)})
    return buf.getvalue()
