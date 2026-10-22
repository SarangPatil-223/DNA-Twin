import ast
import pathlib
import random

import pytest

from app.core.binary import pack_container, unpack_container
from app.core.codec_base import (CodecStatus, DuplicateConflictError, FrameCodec, get_codec,
                                 list_codecs)
from app.core.constraints import ConstraintStatus
from app.core.oligo import (MissingOligosError, Oligo, OligoLayout, build_frames, parse_frame)


def test_layout_validation():
    with pytest.raises(ValueError):
        OligoLayout(payload_bytes=4)
    with pytest.raises(ValueError):
        OligoLayout(forward_primer="ACGN")
    assert OligoLayout(payload_bytes=16, index_bytes=3).frame_bytes == 21


def test_frames_carry_index_and_valid_crc():
    lay = OligoLayout(payload_bytes=10)
    frames = build_frames(b"x" * 55, lay)
    assert len(frames) == 7  # (8 length prefix + 55) / 10 -> 7
    for i, f in enumerate(frames):
        p = parse_frame(f, lay)
        assert p.index == i and p.crc_ok


def test_too_many_frames_rejected():
    with pytest.raises(ValueError):
        build_frames(b"x" * 3000, OligoLayout(payload_bytes=8, index_bytes=1))


@pytest.fixture
def codec():
    return get_codec("raw2bit", layout=OligoLayout(payload_bytes=16, forward_primer="ACACGACGCTCTTCCGATCT",
                                                   reverse_primer="AGATCGGAAGAGCGGTTCAG"))


def test_zero_noise_end_to_end(sample, codec):
    """file -> container -> oligos -> nucleotides -> oligos -> container -> byte-exact file."""
    name, mime, data = sample
    blob = pack_container(data, name, mime, codec.name)
    oligos = codec.encode(blob)
    assert all(set(o.sequence) <= set("ACGT") for o in oligos)
    assert len({len(o) for o in oligos}) == 1  # fixed length
    assert len(oligos[0]) == 20 + 4 * 21 + 20
    shuffled = oligos[:]
    random.Random(1).shuffle(shuffled)  # order must not matter: the index does the work
    res = unpack_container(codec.decode(shuffled))
    assert res.sha256_ok and res.data == data and res.metadata.filename == name


def test_crc_detects_substitution_and_reports_missing(codec):
    blob = pack_container(b"detect me" * 30, "d.txt")
    oligos = codec.encode(blob)
    victim = oligos[3]
    pos = 20 + 30  # inside the coded region
    swap = {"A": "C", "C": "G", "G": "T", "T": "A"}
    oligos[3] = Oligo(victim.index, victim.sequence[:pos] + swap[victim.sequence[pos]] + victim.sequence[pos + 1:])
    with pytest.raises(MissingOligosError) as ei:
        codec.decode(oligos)
    assert ei.value.missing == [3] and ei.value.expected == len(oligos)
    assert codec.last_report.crc_failures == 1


def test_dropout_and_undecodable(codec):
    oligos = codec.encode(pack_container(b"z" * 200, "z.bin"))
    del oligos[5]
    oligos.append(Oligo(99, "ACGT"))  # wrong length
    with pytest.raises(MissingOligosError) as ei:
        codec.decode(oligos)
    assert ei.value.missing == [5] and codec.last_report.undecodable == 1


def test_missing_frame_zero(codec):
    with pytest.raises(MissingOligosError) as ei:
        codec.decode(codec.encode(b"abc" * 20)[1:])
    assert ei.value.missing == [0]


def test_duplicates_ok_conflicts_raise(codec):
    oligos = codec.encode(b"dup" * 40)
    assert codec.decode(oligos + oligos[:3]) == b"dup" * 40
    assert codec.last_report.duplicates == 3
    other = codec.encode(b"DUP" * 40)
    with pytest.raises(DuplicateConflictError):
        codec.decode(oligos + [other[1]])


def test_constraint_report_flags_raw2bit_homopolymers(codec):
    # 0x00 bytes map to AAAA: the reference codec makes no attempt to avoid homopolymers
    rep = codec.constraints_satisfied(codec.encode(b"\x00" * 200))
    assert rep.status is ConstraintStatus.INVALID and rep.violation_counts["homopolymer"] > 0


def test_registry_and_status_honesty():
    infos = {c["name"]: c for c in list_codecs()}
    assert infos["raw2bit"]["status"] == CodecStatus.IMPLEMENTED.value
    with pytest.raises(KeyError):
        get_codec("nope")


def test_frame_codec_is_abstract():
    with pytest.raises(TypeError):
        FrameCodec()  # type: ignore[abstract]


def test_core_has_no_web_or_db_imports():
    forbidden = {"fastapi", "sqlalchemy", "alembic", "psycopg", "psycopg2", "qdrant_client", "starlette", "httpx", "requests"}
    core = pathlib.Path(__file__).resolve().parents[2] / "app" / "core"
    for py in core.rglob("*.py"):
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module]
            for n in names:
                assert n.split(".")[0] not in forbidden, f"{py.name} imports {n}"
