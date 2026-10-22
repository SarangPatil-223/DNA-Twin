#!/usr/bin/env python
"""CLI benchmark: python scripts/benchmark.py FILE [--codecs ...] [--rates ...] [--seeds N] --out results.csv

Writes per-run rows and a mean/std summary. SIMULATION ONLY."""
import argparse
import mimetypes
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.core.benchmark import SweepConfig, run_sweep, to_csv  # noqa: E402
from app.core.codec_base import runnable_codecs  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--codecs", nargs="*", default=runnable_codecs())
    ap.add_argument("--rates", nargs="*", type=float, default=[0.0, 0.005, 0.01, 0.03, 0.05, 0.10])
    ap.add_argument("--rs", nargs="*", type=float, default=[0.0, 30.0])
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--copies", type=int, default=5)
    ap.add_argument("--dropout", type=float, default=0.02)
    ap.add_argument("--out", default="benchmark.csv")
    a = ap.parse_args()
    p = pathlib.Path(a.file)
    data = p.read_bytes()
    mime = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    cfg = SweepConfig(codecs=a.codecs, error_rates=a.rates, rs_levels=a.rs, seeds=list(range(1, a.seeds + 1)),
                      copies=a.copies, dropout=a.dropout)
    res = run_sweep(data, p.name, mime, cfg, progress=lambda d, t: print(f"\r{d}/{t}", end="", file=sys.stderr))
    print(file=sys.stderr)
    pathlib.Path(a.out).write_text(to_csv(res["rows"]))
    summary = pathlib.Path(a.out).with_name(pathlib.Path(a.out).stem + "_summary.csv")
    summary.write_text(to_csv(res["summary"]))
    print(f"rows -> {a.out}\nsummary -> {summary}")
    for r in res["summary"]:
        if r["error_rate"] == max(cfg.error_rates):
            print(f"{r['variant']:16} tolerance={r['error_tolerance']} density={r['density_bits_per_nt']:.3f}")


if __name__ == "__main__":
    main()
