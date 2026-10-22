"""Biochemical constraint checks on nucleotide sequences.

These are the constraints DNA-storage papers design around: GC balance (synthesis/PCR bias),
homopolymer runs (sequencing error hotspots, especially nanopore), and sequence complexity.
Thresholds are configurable; defaults follow common practice (GC 40-60 %, homopolymer <= 3).

Every violation reports the exact constraint, the measured value and the threshold it broke.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Iterable


class ConstraintStatus(str, Enum):
    VALID = "VALID"
    WARNING = "WARNING"
    INVALID = "INVALID"


_RANK = {ConstraintStatus.VALID: 0, ConstraintStatus.WARNING: 1, ConstraintStatus.INVALID: 2}


@dataclass(frozen=True)
class ConstraintThresholds:
    gc_valid: tuple[float, float] = (0.40, 0.60)  # inside → VALID
    gc_warning: tuple[float, float] = (0.30, 0.70)  # inside but outside valid → WARNING, else INVALID
    homopolymer_valid: int = 3  # runs <= this are VALID
    homopolymer_warning: int = 5  # runs <= this are WARNING, longer are INVALID
    entropy_valid: float = 1.90  # Shannon entropy bits/nt (max 2.0)
    entropy_warning: float = 1.50  # kept for API compatibility; entropy never makes a sequence INVALID
    gc_window: int = 20  # local GC window; 0 disables
    local_gc_warning: tuple[float, float] = (0.20, 0.80)  # local windows outside → WARNING only

    def __post_init__(self) -> None:
        if not (self.gc_warning[0] <= self.gc_valid[0] <= self.gc_valid[1] <= self.gc_warning[1]):
            raise ValueError("gc_valid must sit inside gc_warning")
        if self.homopolymer_valid > self.homopolymer_warning:
            raise ValueError("homopolymer_valid must be <= homopolymer_warning")
        if self.entropy_warning > self.entropy_valid:
            raise ValueError("entropy_warning must be <= entropy_valid")


@dataclass(frozen=True)
class Violation:
    constraint: str  # "gc_content" | "homopolymer" | "entropy" | "local_gc" | "alphabet"
    severity: ConstraintStatus
    value: float
    threshold: str  # human-readable bound that was broken
    position: int | None = None  # 0-based start where applicable
    detail: str = ""


@dataclass
class ConstraintReport:
    status: ConstraintStatus
    length: int
    gc_content: float
    max_homopolymer: int
    entropy: float
    violations: list[Violation] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        for v in d["violations"]:
            v["severity"] = v["severity"].value
        return d


# --------------------------------------------------------------------------- measurements


def gc_content(seq: str) -> float:
    if not seq:
        return 0.0
    return (seq.count("G") + seq.count("C")) / len(seq)


def homopolymer_runs(seq: str) -> list[tuple[str, int, int]]:
    """All runs as (base, start, length)."""
    runs: list[tuple[str, int, int]] = []
    if not seq:
        return runs
    start = 0
    for i in range(1, len(seq) + 1):
        if i == len(seq) or seq[i] != seq[start]:
            runs.append((seq[start], start, i - start))
            start = i
    return runs


def max_homopolymer(seq: str) -> int:
    return max((r[2] for r in homopolymer_runs(seq)), default=0)


def shannon_entropy(seq: str) -> float:
    """Bits per nucleotide over single-base frequencies (0 .. 2)."""
    if not seq:
        return 0.0
    n = len(seq)
    return -sum((c / n) * math.log2(c / n) for c in Counter(seq).values())


def windowed_gc(seq: str, window: int) -> list[float]:
    if window <= 0 or len(seq) < window:
        return []
    gc = [1 if b in "GC" else 0 for b in seq]
    s = sum(gc[:window])
    out = [s / window]
    for i in range(window, len(seq)):
        s += gc[i] - gc[i - window]
        out.append(s / window)
    return out


# --------------------------------------------------------------------------- checks


def _band(value: float, valid: tuple[float, float], warning: tuple[float, float]) -> ConstraintStatus:
    if valid[0] <= value <= valid[1]:
        return ConstraintStatus.VALID
    if warning[0] <= value <= warning[1]:
        return ConstraintStatus.WARNING
    return ConstraintStatus.INVALID


def check_sequence(seq: str, t: ConstraintThresholds | None = None) -> ConstraintReport:
    t = t or ConstraintThresholds()
    seq = seq.upper()
    violations: list[Violation] = []

    bad = sorted(set(seq) - set("ACGT"))
    if bad:
        violations.append(
            Violation("alphabet", ConstraintStatus.INVALID, len(bad), "only A/C/G/T allowed",
                      seq.find(bad[0]), f"illegal characters {bad}")
        )

    gc = gc_content(seq)
    sev = _band(gc, t.gc_valid, t.gc_warning)
    if sev is not ConstraintStatus.VALID:
        bound = t.gc_valid if sev is ConstraintStatus.WARNING else t.gc_warning
        violations.append(Violation("gc_content", sev, round(gc, 4), f"{bound[0]:.2f}–{bound[1]:.2f}"))

    runs = homopolymer_runs(seq)
    longest = max((r[2] for r in runs), default=0)
    for base, start, length in runs:
        if length > t.homopolymer_warning:
            violations.append(Violation("homopolymer", ConstraintStatus.INVALID, length,
                                        f"<= {t.homopolymer_warning}", start, f"{base}x{length}"))
        elif length > t.homopolymer_valid:
            violations.append(Violation("homopolymer", ConstraintStatus.WARNING, length,
                                        f"<= {t.homopolymer_valid}", start, f"{base}x{length}"))

    ent = shannon_entropy(seq)
    # Entropy is a low-complexity proxy, not a vendor rule, so it can only raise a WARNING.
    if seq and ent < t.entropy_valid:
        violations.append(Violation("entropy", ConstraintStatus.WARNING, round(ent, 4), f">= {t.entropy_valid}"))

    for pos, g in enumerate(windowed_gc(seq, t.gc_window)):
        if not (t.local_gc_warning[0] <= g <= t.local_gc_warning[1]):
            violations.append(Violation("local_gc", ConstraintStatus.WARNING, round(g, 4),
                                        f"{t.local_gc_warning[0]:.2f}–{t.local_gc_warning[1]:.2f} per {t.gc_window} nt",
                                        pos, "first offending window"))
            break

    status = max((v.severity for v in violations), key=_RANK.__getitem__, default=ConstraintStatus.VALID)
    return ConstraintReport(status, len(seq), round(gc, 4), longest, round(ent, 4), violations)


@dataclass
class BatchConstraintReport:
    status: ConstraintStatus
    n_sequences: int
    counts: dict[str, int]  # VALID/WARNING/INVALID → count
    violation_counts: dict[str, int]  # constraint name → number of sequences breaking it
    mean_gc: float
    max_homopolymer: int
    worst: list[tuple[int, ConstraintReport]]  # up to 10 worst (position in batch, report)

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "n_sequences": self.n_sequences,
            "counts": self.counts,
            "violation_counts": self.violation_counts,
            "mean_gc": self.mean_gc,
            "max_homopolymer": self.max_homopolymer,
            "worst": [{"i": i, **r.to_dict()} for i, r in self.worst],
        }


def check_batch(seqs: Iterable[str], t: ConstraintThresholds | None = None) -> BatchConstraintReport:
    reports = [check_sequence(s, t) for s in seqs]
    counts = {s.value: 0 for s in ConstraintStatus}
    vcounts: dict[str, int] = {}
    for r in reports:
        counts[r.status.value] += 1
        for name in {v.constraint for v in r.violations}:
            vcounts[name] = vcounts.get(name, 0) + 1
    status = max((r.status for r in reports), key=_RANK.__getitem__, default=ConstraintStatus.VALID)
    ranked = sorted(enumerate(reports), key=lambda p: (_RANK[p[1].status], len(p[1].violations)), reverse=True)
    worst = [p for p in ranked if p[1].status is not ConstraintStatus.VALID][:10]
    total = sum(r.length for r in reports)
    mean_gc = sum(r.gc_content * r.length for r in reports) / total if total else 0.0
    return BatchConstraintReport(status, len(reports), counts, vcounts, round(mean_gc, 4),
                                 max((r.max_homopolymer for r in reports), default=0), worst)
