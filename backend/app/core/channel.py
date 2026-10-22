"""Digital-twin noise channel: storage decay + dropout + per-read substitutions, insertions, deletions.

SIMULATION ONLY. The model is deliberately simple and every rate is a user parameter:
  - survival of each oligo species: (1 - dropout) * 0.5 ** (years / half_life_years)
    (a first-order decay; half-life is an assumption the user sets, not a measured constant)
  - each surviving species yields `copies` reads (fixed, or Poisson with that mean)
  - each read gets independent per-base substitution / insertion / deletion events.
The decoder only ever sees the shuffled reads; the true origin of each read is kept separately
for statistics and diff views.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np
from rapidfuzz.distance import Levenshtein

BASES = "ACGT"


@dataclass
class ChannelParams:
    sub: float = 0.0
    ins: float = 0.0
    dele: float = 0.0
    dropout: float = 0.0
    years: float = 0.0
    half_life_years: float = 500.0
    copies: int = 1
    copy_dist: str = "fixed"  # "fixed" | "poisson"
    seed: int = 42

    def __post_init__(self) -> None:
        for name in ("sub", "ins", "dele", "dropout"):
            v = getattr(self, name)
            if not 0 <= v <= 1:
                raise ValueError(f"{name} must be in [0, 1], got {v}")
        if self.sub + self.ins + self.dele > 1:
            raise ValueError("sub + ins + del must be <= 1")
        if self.copies < 1:
            raise ValueError("copies must be >= 1")
        if self.half_life_years <= 0:
            raise ValueError("half_life_years must be > 0")
        if self.copy_dist not in ("fixed", "poisson"):
            raise ValueError("copy_dist must be 'fixed' or 'poisson'")

    @property
    def survival(self) -> float:
        return (1 - self.dropout) * 0.5 ** (self.years / self.half_life_years)

    @property
    def total_error_rate(self) -> float:
        return self.sub + self.ins + self.dele

    @classmethod
    def from_error_rate(cls, rate: float, mix=(0.5, 0.1, 0.4), **kw) -> "ChannelParams":
        """Split one headline rate into sub/ins/del. Default mix 50:10:40 is our assumption
        (deletions dominate synthesis errors; substitutions dominate Illumina reads)."""
        s = sum(mix)
        return cls(sub=rate * mix[0] / s, ins=rate * mix[1] / s, dele=rate * mix[2] / s, **kw)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["survival"] = self.survival
        return d


@dataclass
class ChannelResult:
    reads: list[str]
    origin: list[int]  # true source oligo position per read (hidden from the decoder)
    totals: dict
    per_oligo: list[dict]
    diffs: list[dict] = field(default_factory=list)


def _mutate(seq: str, p: ChannelParams, rng: np.random.Generator) -> tuple[str, int, int, int]:
    n = len(seq)
    if p.total_error_rate == 0 or n == 0:
        return seq, 0, 0, 0
    r = rng.random(n)
    t1, t2, t3 = p.sub, p.sub + p.dele, p.sub + p.dele + p.ins
    events = np.nonzero(r < t3)[0]
    if events.size == 0:
        return seq, 0, 0, 0
    out: list[str] = []
    last = 0
    subs = dels = inss = 0
    for i in events:
        out.append(seq[last:i])
        x = r[i]
        b = seq[i]
        if x < t1:
            out.append(BASES[(BASES.index(b) + 1 + int(rng.integers(3))) % 4] if b in BASES else "A")
            subs += 1
        elif x < t2:
            dels += 1
        else:
            out.append(BASES[int(rng.integers(4))])
            out.append(b)
            inss += 1
        last = i + 1
    out.append(seq[last:])
    return "".join(out), subs, inss, dels


def _diff(orig: str, read: str) -> list[list]:
    """Compact alignment: [op, orig_start, orig_end, read_start, read_end]."""
    return [[op.tag, op.src_start, op.src_end, op.dest_start, op.dest_end]
            for op in Levenshtein.opcodes(orig, read) if op.tag != "equal"]


def simulate(sequences: list[str], p: ChannelParams, diff_samples: int = 12) -> ChannelResult:
    rng = np.random.default_rng(p.seed)
    reads: list[str] = []
    origin: list[int] = []
    per_oligo: list[dict] = []
    tot = {"species": len(sequences), "dropped": 0, "reads": 0, "subs": 0, "ins": 0, "dels": 0,
           "bases_read": 0, "error_free_reads": 0}
    survival = p.survival
    diffs: list[dict] = []
    for idx, seq in enumerate(sequences):
        alive = rng.random() < survival
        n = 0
        if alive:
            n = int(rng.poisson(p.copies)) if p.copy_dist == "poisson" else p.copies
        st = {"i": idx, "copies": n, "dropped": not alive or n == 0, "subs": 0, "ins": 0, "dels": 0}
        if st["dropped"]:
            tot["dropped"] += 1
        for _ in range(n):
            read, s, ins, d = _mutate(seq, p, rng)
            st["subs"] += s
            st["ins"] += ins
            st["dels"] += d
            reads.append(read)
            origin.append(idx)
            tot["bases_read"] += len(seq)
            tot["error_free_reads"] += (s + ins + d) == 0
            if len(diffs) < diff_samples and (s + ins + d) > 0:
                diffs.append({"i": idx, "original": seq, "read": read, "ops": _diff(seq, read)})
        for k in ("subs", "ins", "dels"):
            tot[k] += st[k]
        per_oligo.append(st)
    tot["reads"] = len(reads)
    b = max(tot["bases_read"], 1)
    tot["observed_error_rate"] = (tot["subs"] + tot["ins"] + tot["dels"]) / b
    tot["observed_sub_rate"] = tot["subs"] / b
    tot["observed_ins_rate"] = tot["ins"] / b
    tot["observed_del_rate"] = tot["dels"] / b
    tot["dropout_rate"] = tot["dropped"] / max(len(sequences), 1)
    order = rng.permutation(len(reads))
    return ChannelResult([reads[i] for i in order], [origin[i] for i in order], tot, per_oligo, diffs)
