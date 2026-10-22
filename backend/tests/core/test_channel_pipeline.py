import random

import pytest

from app.core.binary import pack_container
from app.core.channel import ChannelParams, simulate
from app.core.ecc.consensus import alignment_consensus, cluster_reads, majority_consensus
from app.core.pipeline import run_all

def _rand_seq(i: int, n: int = 120) -> str:
    rng = random.Random(i)
    return "".join(rng.choice("ACGT") for _ in range(n))


SEQS = [_rand_seq(i) for i in range(40)]


def test_zero_noise_channel_is_identity():
    r = simulate(SEQS, ChannelParams(copies=3, seed=1))
    assert sorted(r.reads) == sorted(s for s in SEQS for _ in range(3))
    assert r.totals["observed_error_rate"] == 0 and r.totals["dropped"] == 0


def test_seed_reproducibility():
    p = ChannelParams(sub=0.02, ins=0.01, dele=0.01, dropout=0.1, copies=4, seed=99)
    a, b = simulate(SEQS, p), simulate(SEQS, p)
    assert a.reads == b.reads and a.totals == b.totals
    c = simulate(SEQS, ChannelParams(sub=0.02, ins=0.01, dele=0.01, dropout=0.1, copies=4, seed=100))
    assert c.reads != a.reads


@pytest.mark.parametrize("kind", ["sub", "ins", "dele"])
def test_each_error_type_in_isolation(kind):
    p = ChannelParams(**{kind: 0.05}, copies=5, seed=3)
    r = simulate(SEQS, p)
    t = r.totals
    other = {"sub": ("ins", "dels"), "ins": ("subs", "dels"), "dele": ("subs", "ins")}[kind]
    assert all(t[o] == 0 for o in other)
    assert t["observed_error_rate"] == pytest.approx(0.05, abs=0.01)
    lens = {len(x) for x in r.reads}
    if kind == "sub":
        assert lens == {120}
    elif kind == "ins":
        assert max(lens) > 120 and min(lens) >= 120
    else:
        assert min(lens) < 120 and max(lens) <= 120


def test_dropout_and_decay():
    r = simulate(SEQS * 25, ChannelParams(dropout=0.2, seed=5))
    assert r.totals["dropout_rate"] == pytest.approx(0.2, abs=0.05)
    p = ChannelParams(years=500, half_life_years=500)
    assert p.survival == pytest.approx(0.5)


def test_param_validation():
    with pytest.raises(ValueError):
        ChannelParams(sub=1.5)
    with pytest.raises(ValueError):
        ChannelParams(copies=0)


def test_consensus_repairs_each_error_type():
    ref = SEQS[0]
    reads = [ref[:10] + "T" + ref[11:], ref[:50] + ref[51:], ref[:80] + "G" + ref[80:], ref, ref[:100] + ref[101:]]
    assert alignment_consensus(reads, 120) == ref
    assert majority_consensus([ref, ref, ref[:5] + ("A" if ref[5] != "A" else "C") + ref[6:]]) == ref


def test_clustering_groups_copies_without_origin():
    r = simulate(SEQS, ChannelParams(sub=0.01, dele=0.005, ins=0.005, copies=6, seed=8))
    clusters, st = cluster_reads(r.reads, max_key_dist=4)
    assert st.clusters <= len(SEQS) * 1.3
    # purity: most clusters should hold reads from one origin
    origin = {}
    for read, o in zip(r.reads, r.origin):
        origin.setdefault(read, set()).add(o)
    pure = sum(len(set().union(*(origin[x] for x in c))) == 1 for c in clusters)
    assert pure / len(clusters) > 0.9


@pytest.mark.parametrize("codec,kw", [("church", {"rs_parity_pct": 30}), ("yinyang", {"rs_parity_pct": 30}),
                                      ("goldman", {}), ("fountain", {"overhead": 0.4}), ("raw2bit", {"rs_parity_pct": 30})])
def test_full_flow_recovers_exactly_at_1pct_with_coverage(sample, codec, kw):
    name, mime, data = sample
    res = run_all(data, name, mime, codec, ChannelParams.from_error_rate(0.01, copies=6, seed=11), kw)
    ret = res["retrieval"]
    assert ret.exact_match, (codec, ret.metrics, ret.notes)
    assert ret.recovered_file == data


def test_failure_is_reported_not_hidden():
    data = bytes(random.Random(0).randbytes(2000))
    res = run_all(data, "r.bin", "application/octet-stream", "church", ChannelParams.from_error_rate(0.10, copies=1, seed=2))
    ret = res["retrieval"]
    assert not ret.exact_match
    assert ret.metrics["units_unrecoverable"] > 0
    assert ret.label == "Simulation Result"
