"""Read clustering and consensus — ERROR CORRECTION across physical copies.

Clustering never uses the true origin of a read. Reads are grouped by a key made of both ends of
the read (where every codec here keeps its index / seed / orientation marker): exact key matches
first, then leftover reads join the nearest cluster whose key is within `max_key_dist` edits.

Consensus per cluster:
  majority  — reads of the modal length vote per position (reads with indels are ignored)
  alignment — every read is aligned to a reference with edit-distance opcodes, votes are cast per
              reference column including gaps, and the process repeats once on the new consensus
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

import numpy as np
from rapidfuzz import process
from rapidfuzz.distance import Levenshtein

_IDX = {c: i for i, c in enumerate("ACGT")}
GAP = 4


@dataclass
class ClusterStats:
    reads: int
    clusters: int
    exact_key_reads: int
    merged_reads: int
    singletons: int
    mean_size: float

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def key_distance_for(error_rate: float, key_len: int = 20) -> int:
    """Merge threshold for keys that match at neither end: ~4x the expected edits in a
    2*key_len key, at least 3 when there is any noise, capped at 8."""
    if error_rate <= 0:
        return 0
    return int(min(8, max(3, round(2 * key_len * error_rate * 4))))


def _key(read: str, k: int) -> str:
    return read[:k] + read[-k:] if len(read) > 2 * k else read


def cluster_reads(reads: list[str], key_len: int = 20, max_key_dist: int = 4,
                  trim: tuple[int, int] = (0, 0)) -> tuple[list[list[str]], ClusterStats]:
    """Group reads that came from the same oligo, without knowing their origin.

    1. reads with an identical (prefix + suffix) key form seed groups;
    2. groups seen more than once become cluster representatives;
    3. every remaining read joins the representative with the nearest key (Levenshtein, so an
       indel costs ~2 edits rather than scrambling the key) within `max_key_dist`, else it
       starts its own cluster. Neighbouring oligos differ in their CRC/seed end, which keeps
       their keys far apart even when their index ends look alike.
    `trim` removes constant primer regions first (primers carry no identity)."""
    f, r_ = trim
    groups: dict[str, list[str]] = defaultdict(list)
    for r in reads:
        core = r[f : len(r) - r_ if r_ else None]
        groups[_key(core, key_len)].append(r)
    ordered = sorted(groups.items(), key=lambda kv: -len(kv[1]))
    rep_keys: list[str] = []
    clusters: list[list[str]] = []
    merged = exact = 0

    def add_rep(key: str, members: list[str]) -> None:
        idx = len(clusters)
        rep_keys.append(key)
        clusters.append(list(members))

    for key, members in ordered:
        if len(members) > 1 or not rep_keys:
            add_rep(key, members)
            exact += len(members)
            continue
        target = None
        if max_key_dist > 0:
            hit = process.extractOne(key, rep_keys, scorer=Levenshtein.distance, score_cutoff=max_key_dist)
            target = hit[2] if hit is not None else None
        if target is None:
            add_rep(key, members)
            exact += len(members)
        else:
            clusters[target].extend(members)
            merged += len(members)
    sizes = [len(c) for c in clusters]
    stats = ClusterStats(len(reads), len(clusters), exact, merged, sum(s == 1 for s in sizes),
                         round(float(np.mean(sizes)), 3) if sizes else 0.0)
    return clusters, stats


def majority_consensus(cluster: list[str], expected_len: int | None = None) -> str:
    if len(cluster) == 1:
        return cluster[0]
    lens = Counter(len(r) for r in cluster)
    target = expected_len if expected_len in lens else lens.most_common(1)[0][0]
    same = [r for r in cluster if len(r) == target]
    arr = np.array([[_IDX.get(c, 0) for c in r] for r in same], dtype=np.int8)
    counts = np.stack([(arr == b).sum(axis=0) for b in range(4)], axis=1)
    return "".join("ACGT"[i] for i in counts.argmax(axis=1))


def _align_votes(ref: str, reads: list[str]) -> tuple[np.ndarray, dict[int, Counter]]:
    """Per-column votes (A,C,G,T,gap) and, per gap between columns, the strings reads insert there."""
    votes = np.zeros((len(ref), 5), dtype=np.int32)
    inserts: dict[int, Counter] = defaultdict(Counter)
    for r in reads:
        for op in Levenshtein.opcodes(ref, r):
            if op.tag in ("equal", "replace"):
                span = min(op.src_end - op.src_start, op.dest_end - op.dest_start)
                for t in range(span):
                    votes[op.src_start + t, _IDX.get(r[op.dest_start + t], 0)] += 1
                if op.src_end - op.src_start > span:
                    votes[op.src_start + span : op.src_end, GAP] += 1
            elif op.tag == "delete":
                votes[op.src_start : op.src_end, GAP] += 1
            elif op.tag == "insert":
                inserts[op.src_start][r[op.dest_start : op.dest_end]] += 1
    return votes, inserts


def alignment_consensus(cluster: list[str], expected_len: int | None = None, rounds: int = 3) -> str:
    if len(cluster) == 1:
        return cluster[0]
    if len(cluster) == 2 and len(cluster[0]) == len(cluster[1]):
        return cluster[0]  # a tie cannot be broken; keep one read and let CRC/RS decide
    lens = Counter(len(r) for r in cluster)
    target = expected_len if expected_len in lens else lens.most_common(1)[0][0]
    ref = next(r for r in cluster if len(r) == target)
    half = len(cluster) / 2
    for _ in range(rounds):
        votes, inserts = _align_votes(ref, cluster)
        best = votes.argmax(axis=1)
        out: list[str] = []
        for j in range(len(ref) + 1):
            if j in inserts:
                ins, n = inserts[j].most_common(1)[0]
                if n > half:  # most reads carry a base the reference is missing
                    out.append(ins)
            if j < len(ref) and best[j] != GAP:
                out.append("ACGT"[best[j]])
        new = "".join(out)
        if new == ref:
            break
        ref = new
    return ref


def consensus_all(clusters: list[list[str]], method: str = "alignment", expected_len: int | None = None) -> list[str]:
    if method not in ("majority", "alignment"):
        raise ValueError("method must be 'majority' or 'alignment'")
    fn = majority_consensus if method == "majority" else alignment_consensus
    return [fn(c, expected_len) for c in clusters]
