"""Benchmark sweep: codec x error rate x redundancy x seeds -> rows + mean/std summary.

Every number comes from an actual run. Error tolerance is reported as the highest tested error
rate at which EVERY seed recovered the file byte-exactly (SHA-256) — never interpolated.
"""

from __future__ import annotations

import csv
import io
import statistics
import time
from dataclasses import dataclass, field
from typing import Callable

from . import SIMULATION_LABEL
from .channel import ChannelParams
from .codec_base import codec_class
from .pipeline import encode_file, retrieve, run_channel


@dataclass
class SweepConfig:
    codecs: list[str]
    error_rates: list[float] = field(default_factory=lambda: [0.0, 0.005, 0.01, 0.03, 0.05, 0.10])
    rs_levels: list[float] = field(default_factory=lambda: [0.0, 30.0])
    seeds: list[int] = field(default_factory=lambda: [1, 2, 3])
    copies: int = 5
    dropout: float = 0.02
    mix: tuple[float, float, float] = (0.5, 0.1, 0.4)
    consensus: str = "alignment"
    compress: bool = False
    fountain_overhead: float = 0.4


def _variants(cfg: SweepConfig) -> list[tuple[str, dict, str]]:
    out = []
    for name in cfg.codecs:
        cls = codec_class(name)
        if cls.supports_rs:
            for rs in cfg.rs_levels:
                out.append((name, {"rs_parity_pct": rs} if rs else {}, f"{name}+rs{int(rs)}" if rs else name))
        elif name == "fountain":
            out.append((name, {"overhead": cfg.fountain_overhead}, name))
        else:
            out.append((name, {}, name))
    return out


def run_sweep(data: bytes, filename: str, mime: str, cfg: SweepConfig,
              extra: Callable[[bytes, bytes | None, str], dict] | None = None,
              progress: Callable[[int, int], None] | None = None) -> dict:
    variants = _variants(cfg)
    total = len(variants) * len(cfg.error_rates) * len(cfg.seeds)
    rows: list[dict] = []
    done = 0
    for name, params, variant in variants:
        enc = encode_file(data, filename, mime, name, params, cfg.compress)
        exp_len = len(enc.oligos[0].sequence) if enc.oligos else None
        for rate in cfg.error_rates:
            for seed in cfg.seeds:
                ch_params = ChannelParams.from_error_rate(rate, mix=cfg.mix, copies=cfg.copies,
                                                          dropout=cfg.dropout if rate > 0 else 0.0, seed=seed)
                ch, sim_ms = run_channel(enc.sequences, ch_params)
                t0 = time.perf_counter()
                ret = retrieve(name, params, enc.manifest, ch.reads, enc.container, data, cfg.consensus, rate, exp_len)
                row = {
                    "codec": name, "variant": variant, "rs_parity_pct": params.get("rs_parity_pct", 0.0),
                    "error_rate": rate, "seed": seed, "copies": cfg.copies, "dropout": ch_params.dropout,
                    "exact_match": int(ret.exact_match),
                    "file_byte_accuracy": ret.metrics["file_byte_accuracy"],
                    "file_bit_accuracy": ret.metrics["file_bit_accuracy"],
                    "density_bits_per_nt": enc.stats["density_bits_per_nt"],
                    "n_oligos": enc.stats["n_oligos"], "total_nt": enc.stats["total_nt"],
                    "oligo_len": enc.stats["oligo_len"], "gc": enc.stats["gc"],
                    "max_homopolymer": enc.constraints["max_homopolymer"],
                    "constraint_status": enc.constraints["status"],
                    "encode_ms": enc.encode_ms, "sim_ms": sim_ms, "retrieval_ms": ret.metrics["retrieval_ms"],
                    "observed_error_rate": ch.totals["observed_error_rate"],
                    "units_unrecoverable": ret.metrics["units_unrecoverable"],
                    "crc_failures": ret.metrics["crc_failures"],
                }
                if extra is not None:
                    row.update(extra(data, ret.recovered_file if ret.exact_match or ret.recovered_file else None, mime))
                rows.append(row)
                done += 1
                if progress:
                    progress(done, total)
    return {"label": SIMULATION_LABEL, "rows": rows, "summary": summarize(rows), "config": cfg.__dict__}


def _ms(values: list[float]) -> tuple[float | None, float | None]:
    vals = [v for v in values if v is not None]
    if not vals:
        return None, None
    return statistics.fmean(vals), (statistics.stdev(vals) if len(vals) > 1 else 0.0)


def summarize(rows: list[dict]) -> list[dict]:
    """One row per variant x error rate with mean and std over seeds, plus per-variant tolerance."""
    groups: dict[tuple, list[dict]] = {}
    for r in rows:
        groups.setdefault((r["variant"], r["error_rate"]), []).append(r)
    out = []
    numeric = ["exact_match", "file_byte_accuracy", "file_bit_accuracy", "retrieval_ms", "observed_error_rate"]
    extra_keys = sorted({k for r in rows for k in r if k.startswith("llm_")})
    for (variant, rate), rs in sorted(groups.items()):
        first = rs[0]
        s = {"variant": variant, "codec": first["codec"], "rs_parity_pct": first["rs_parity_pct"],
             "error_rate": rate, "n_seeds": len(rs), "density_bits_per_nt": first["density_bits_per_nt"],
             "gc": first["gc"], "max_homopolymer": first["max_homopolymer"],
             "constraint_status": first["constraint_status"], "encode_ms": first["encode_ms"]}
        for k in numeric + extra_keys:
            m, sd = _ms([r.get(k) for r in rs])
            s[f"{k}_mean"], s[f"{k}_std"] = m, sd
        out.append(s)
    tol: dict[str, float] = {}
    for variant in {r["variant"] for r in out}:
        ok = [r["error_rate"] for r in out if r["variant"] == variant and r["exact_match_mean"] == 1.0]
        # tolerance = highest rate where all lower tested rates also succeeded
        rates = sorted(r["error_rate"] for r in out if r["variant"] == variant)
        best = None
        for rate in rates:
            if rate in ok:
                best = rate
            else:
                break
        tol[variant] = best
    for r in out:
        r["error_tolerance"] = tol[r["variant"]]
    return out


def to_csv(rows: list[dict]) -> str:
    if not rows:
        return ""
    keys: list[str] = []
    for r in rows:
        for k in r:
            if k not in keys:
                keys.append(k)
    buf = io.StringIO()
    buf.write(f"# {SIMULATION_LABEL} - DNA Twin benchmark, simulated channel, not wet-lab data\n")
    w = csv.DictWriter(buf, fieldnames=keys)
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()
