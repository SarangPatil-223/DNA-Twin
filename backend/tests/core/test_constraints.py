import pytest

from app.core.constraints import (ConstraintStatus as S, ConstraintThresholds, check_batch,
                                  check_sequence, gc_content, homopolymer_runs, max_homopolymer,
                                  shannon_entropy, windowed_gc)


def test_gc_content():
    assert gc_content("") == 0.0
    assert gc_content("GGCC") == 1.0
    assert gc_content("ACGT") == 0.5
    assert gc_content("AATT") == 0.0


def test_homopolymer():
    assert max_homopolymer("") == 0
    assert max_homopolymer("A") == 1
    assert max_homopolymer("ACGT") == 1
    assert max_homopolymer("AAACGTTTTT") == 5
    assert homopolymer_runs("AACCC") == [("A", 0, 2), ("C", 2, 3)]


def test_entropy():
    assert shannon_entropy("AAAA") == 0.0
    assert shannon_entropy("ACGT") == pytest.approx(2.0)
    assert shannon_entropy("AC" * 10) == pytest.approx(1.0)


def test_windowed_gc():
    assert windowed_gc("GGAA", 2) == [1.0, 0.5, 0.0]
    assert windowed_gc("GG", 5) == []


def test_valid_sequence():
    r = check_sequence("ACGTACGTTGCAAGCTTCGAGATC" * 3)
    assert r.status is S.VALID and r.violations == []


def test_homopolymer_warning_then_invalid_with_position():
    base = "ACGTTGCA" * 4
    w = check_sequence(base[:9] + "GGGG" + base[9:])  # neighbours A and C
    hp = [v for v in w.violations if v.constraint == "homopolymer"]
    assert w.status is S.WARNING and hp[0].value == 4 and hp[0].position == 9 and hp[0].detail == "Gx4"
    inv = check_sequence(base[:10] + "TTTTTTT" + base[10:])
    assert inv.status is S.INVALID
    assert any(v.constraint == "homopolymer" and v.severity is S.INVALID and v.value == 7 for v in inv.violations)


def test_gc_bands():
    t = ConstraintThresholds(gc_window=0, entropy_valid=0, entropy_warning=0, homopolymer_valid=99, homopolymer_warning=99)
    def seq(gc, n=100):
        k = round(gc * n)
        return ("GC" * n)[:k] + ("AT" * n)[: n - k]
    assert check_sequence(seq(0.50), t).status is S.VALID
    for gc, want in [(0.65, S.WARNING), (0.35, S.WARNING), (0.80, S.INVALID), (0.10, S.INVALID)]:
        r = check_sequence(seq(gc), t)
        assert r.status is want, gc
        v = r.violations[0]
        assert v.constraint == "gc_content" and v.value == pytest.approx(gc)


def test_low_entropy_and_alphabet():
    t = ConstraintThresholds(gc_window=0)
    r = check_sequence("ACACACACACACACACACAC", t)  # entropy 1.0, GC 0.5
    assert r.status is S.WARNING and r.violations[0].constraint == "entropy"  # proxy rule: warning only
    bad = check_sequence("ACGTNACGT")
    assert bad.status is S.INVALID and any(v.constraint == "alphabet" and v.position == 4 for v in bad.violations)


def test_local_gc_window_is_warning_only():
    seq = "ACGTTGCAAGCT" * 3 + "G" * 3 + "C" * 3 + "GCGCGCGCGCGC" + "ATATATATATAT" + "TACGGCAT" * 3
    r = check_sequence(seq, ConstraintThresholds(gc_valid=(0.3, 0.7), gc_warning=(0.2, 0.8)))
    lv = [v for v in r.violations if v.constraint == "local_gc"]
    assert lv and lv[0].severity is S.WARNING


def test_threshold_validation():
    with pytest.raises(ValueError):
        ConstraintThresholds(gc_valid=(0.2, 0.8), gc_warning=(0.3, 0.7))


def test_batch():
    good = "ACGTTGCAAGCTTCGAGATCACGT"
    rep = check_batch([good, good[:10] + "AAAA" + good[10:], "A" * 20])
    assert rep.status is S.INVALID and rep.n_sequences == 3
    assert rep.counts == {"VALID": 1, "WARNING": 1, "INVALID": 1}
    assert rep.worst[0][0] == 2
    assert rep.to_dict()["status"] == "INVALID"
