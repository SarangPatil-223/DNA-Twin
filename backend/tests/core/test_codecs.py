import random

import pytest

from app.core.binary import pack_container, unpack_container
from app.core.codec_base import CodecStatus, get_codec, list_codecs, runnable_codecs
from app.core.codecs.goldman import bytes_to_trits, rotate_decode, rotate_encode, trits_to_bytes
from app.core.constraints import max_homopolymer
from app.core.oligo import MissingOligosError

CONFIGS = [("church", {}), ("church", {"rs_parity_pct": 25}), ("raw2bit", {}), ("raw2bit", {"rs_parity_pct": 25}),
           ("yinyang", {}), ("yinyang", {"rs_parity_pct": 25}), ("goldman", {}), ("fountain", {}),
           ("church", {"primers": True})]


def test_every_runnable_codec_is_covered():
    assert {c for c, _ in CONFIGS} == set(runnable_codecs())


@pytest.mark.parametrize("name,kw", CONFIGS, ids=[f"{n}-{k}" for n, k in CONFIGS])
def test_zero_noise_roundtrip(sample, name, kw):
    fname, mime, data = sample
    blob = pack_container(data, fname, mime, name)
    c = get_codec(name, **kw)
    oligos = c.encode(blob)
    assert all(set(o.sequence) <= set("ACGT") for o in oligos)
    random.Random(3).shuffle(oligos)
    res = unpack_container(c.decode(oligos, c.manifest))
    assert res.sha256_ok and res.data == data


@pytest.mark.parametrize("name,kw", [("church", {"rs_parity_pct": 25}), ("yinyang", {"rs_parity_pct": 25}),
                                     ("raw2bit", {"rs_parity_pct": 10})])
def test_rs_recovers_designed_loss_and_fails_beyond(name, kw):
    data = bytes(random.Random(1).randbytes(3000))
    c = get_codec(name, **kw)
    oligos = c.encode(data)
    r = c.manifest.params["rs_r"]
    k = c.manifest.params["rs_k"]
    # drop exactly r oligos from block 0 (data + parity mixed) -> must recover
    block0 = list(range(k)) + list(range(c.manifest.n_units, c.manifest.n_units + r))
    drop = set(random.Random(2).sample(block0, r))
    kept = [o for o in oligos if o.index not in drop]
    assert c.decode(kept, c.manifest) == data
    assert c.last_report.corrected_units == len([d for d in drop if d < c.manifest.n_units])
    # one more loss than designed, all in data frames of block 0 -> must fail honestly
    drop2 = set(range(r + 1))
    with pytest.raises(MissingOligosError):
        c.decode([o for o in oligos if o.index not in drop2], c.manifest)
    partial = c.decode([o for o in oligos if o.index not in drop2], c.manifest, best_effort=True)
    assert len(partial) == len(data) and not c.last_report.complete


def test_no_rs_means_any_loss_is_fatal():
    c = get_codec("church")
    oligos = c.encode(b"x" * 500)
    with pytest.raises(MissingOligosError):
        c.decode(oligos[1:], c.manifest)


def test_church_constraints_by_construction():
    c = get_codec("church")
    for o in c.encode(b"\x00" * 400 + b"\xff" * 400):
        assert max_homopolymer(o.sequence) <= 3
        gc = sum(b in "GC" for b in o.sequence) / len(o.sequence)
        assert 0.4 <= gc <= 0.6


def test_goldman_no_homopolymers_and_rotating_code():
    assert rotate_decode(rotate_encode([0, 1, 2, 2, 0, 1])) == [0, 1, 2, 2, 0, 1]
    assert rotate_decode("AAC") is None
    trits = bytes_to_trits(bytes(range(256)))
    assert trits_to_bytes(trits)[0] == bytes(range(256))
    c = get_codec("goldman")
    for o in c.encode(b"\x00" * 300):
        assert max_homopolymer(o.sequence) == 1


def test_goldman_survives_lost_fragments_via_overlap():
    data = bytes(random.Random(5).randbytes(600))
    c = get_codec("goldman")
    oligos = c.encode(data)
    # drop every 4th fragment; the first and last are kept because the file's first and last
    # 25 trits are covered by a single fragment (same edge effect as in the paper's layout)
    last = len(oligos) - 1
    kept = [o for o in oligos if o.index in (0, last) or o.index % 4 != 2]
    assert c.decode(kept, c.manifest) == data


def test_fountain_screening_and_loss_tolerance():
    data = bytes(random.Random(7).randbytes(2000))
    c = get_codec("fountain", overhead=0.5)
    oligos = c.encode(data)
    for o in oligos:
        gc = sum(b in "GC" for b in o.sequence) / len(o.sequence)
        assert 0.45 <= gc <= 0.55 and max_homopolymer(o.sequence) <= 3
    rng = random.Random(8)
    kept = [o for o in oligos if rng.random() > 0.10]  # lose ~10%
    assert c.decode(kept, c.manifest) == data


def test_yinyang_screening_prefers_valid_masks():
    c = get_codec("yinyang")
    oligos = c.encode(b"\x00" * 800)
    ok = sum(0.4 <= sum(b in "GC" for b in o.sequence) / len(o.sequence) <= 0.6 and max_homopolymer(o.sequence) <= 4
             for o in oligos)
    assert ok / len(oligos) > 0.9


def test_future_work_codecs_refuse():
    fw = [c["name"] for c in list_codecs() if c["status"] == CodecStatus.FUTURE_WORK.value]
    assert {"hedges", "dna_aeon"} <= set(fw)
    for name in fw:
        with pytest.raises(NotImplementedError):
            get_codec(name).encode(b"abc")
