"""Abstract Codec interface, the shared FrameCodec helper, and the codec registry.

    Codec.encode(bytes)                                   -> list[Oligo]   (sets codec.manifest)
    Codec.decode(list[Oligo], manifest=None, best_effort) -> bytes         (sets codec.last_report)

The manifest is the small decoder catalogue kept out-of-band (number of data units, data length,
ECC settings), as real DNA archives catalogue pool contents. Without it, FrameCodec falls back to
the in-band length prefix in frame 0.

`status` is honest by rule: "implemented" only if round-trip tests pass, "simplified" for
reduced versions of published schemes, "future_work" for stubs that raise NotImplementedError.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Callable

from .constraints import BatchConstraintReport, ConstraintThresholds, check_batch
from .ecc import reed_solomon as rs
from .oligo import (
    FramingError,
    MissingOligosError,
    Oligo,
    OligoLayout,
    assemble,
    build_frames,
    chunks_to_data,
    parse_frame,
    stream_chunks,
)


class CodecStatus(str, Enum):
    IMPLEMENTED = "implemented"
    SIMPLIFIED = "simplified"
    FUTURE_WORK = "future_work"


class DuplicateConflictError(FramingError):
    """Two CRC-valid frames claim the same index with different payloads."""


@dataclass
class Manifest:
    codec: str
    data_len: int
    n_units: int  # data frames / fragments / source segments
    n_oligos: int
    params: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict | None) -> "Manifest | None":
        return cls(**d) if d else None


@dataclass
class DecodeReport:
    """DETECTION stats (undecodable, crc_failures) and CORRECTION stats (rs_*, voting) kept apart."""

    received: int = 0
    undecodable: int = 0
    crc_failures: int = 0
    duplicates: int = 0
    conflicts: int = 0
    accepted: int = 0
    # correction layer
    ecc: str = "none"
    erasures: int = 0
    corrected_units: int = 0
    unrecoverable_units: list[int] = field(default_factory=list)
    complete: bool = True
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["unrecoverable_units"] = d["unrecoverable_units"][:50]
        d["n_unrecoverable"] = len(self.unrecoverable_units)
        return d


class Codec(ABC):
    name: str = "abstract"
    label: str = "Abstract"
    status: CodecStatus = CodecStatus.FUTURE_WORK
    description: str = ""
    reference: str = ""
    nominal_bits_per_nt: float = 0.0
    supports_rs: bool = False

    def __init__(self) -> None:
        self.manifest: Manifest | None = None
        self.last_report = DecodeReport()

    @abstractmethod
    def encode(self, data: bytes) -> list[Oligo]: ...

    @abstractmethod
    def decode(self, oligos: list[Oligo], manifest: Manifest | None = None, best_effort: bool = False) -> bytes: ...

    def primer_lengths(self) -> tuple[int, int]:
        return (0, 0)

    unit_bytes_param: str | None = None  # manifest param giving bytes of data per unit

    def lost_byte_ranges(self, manifest: Manifest | None = None) -> list[tuple[int, int]]:
        """Byte ranges of the decoded data that the last decode had to zero-fill.
        Units index the `u64 length + data` stream, hence the 8-byte shift."""
        m = manifest or self.manifest
        units = self.last_report.unrecoverable_units
        if not m or not units:
            return []
        width = int(m.params.get(self.unit_bytes_param, 1)) if self.unit_bytes_param else 1
        out = []
        for u in sorted(units):
            a, b = max(0, u * width - 8), max(0, (u + 1) * width - 8)
            if b > a:
                if out and out[-1][1] >= a:
                    out[-1] = (out[-1][0], max(out[-1][1], b))
                else:
                    out.append((a, min(b, m.data_len)))
        return [(a, b) for a, b in out if a < m.data_len]

    def constraints_satisfied(self, oligos: list[Oligo], thresholds: ConstraintThresholds | None = None) -> BatchConstraintReport:
        f, r = self.primer_lengths()
        return check_batch((o.sequence[f : len(o.sequence) - r if r else None] for o in oligos), thresholds)

    @classmethod
    def info(cls) -> dict:
        return {
            "name": cls.name,
            "label": cls.label,
            "status": cls.status.value,
            "description": cls.description,
            "reference": cls.reference,
            "nominal_bits_per_nt": cls.nominal_bits_per_nt,
            "supports_rs": cls.supports_rs,
        }


class FrameCodec(Codec):
    """Uses the shared [index | payload | CRC16] framing, with an optional RS outer code.
    Subclasses only define frame bytes <-> nucleotides."""

    supports_rs = True
    unit_bytes_param = "payload_bytes"

    def __init__(self, layout: OligoLayout | None = None, rs_parity_pct: float = 0.0, payload_bytes: int | None = None,
                 primers: bool = False):
        super().__init__()
        if layout is None:
            kw = {"payload_bytes": payload_bytes or self.default_payload_bytes}
            if primers:
                kw.update(forward_primer=DEFAULT_FWD_PRIMER, reverse_primer=DEFAULT_REV_PRIMER)
            layout = OligoLayout(**kw)
        self.layout = layout
        self.rs_parity_pct = float(rs_parity_pct)

    default_payload_bytes = 16

    @abstractmethod
    def frame_to_nt(self, frame: bytes) -> str: ...

    @abstractmethod
    def nt_to_frame(self, core: str) -> bytes | None: ...

    def primer_lengths(self) -> tuple[int, int]:
        return len(self.layout.forward_primer), len(self.layout.reverse_primer)

    def _strip_primers(self, seq: str) -> str:
        f, r = self.primer_lengths()
        return seq[f : len(seq) - r if r else None]

    def encode(self, data: bytes) -> list[Oligo]:
        chunks = stream_chunks(data, self.layout.payload_bytes)
        p = rs.plan(len(chunks), self.rs_parity_pct)
        parity = rs.encode_parity(chunks, p)
        frames = build_frames(data, self.layout, parity)
        lf, lr = self.layout.forward_primer, self.layout.reverse_primer
        oligos = [
            Oligo(index=i, sequence=lf + self.frame_to_nt(fr) + lr, codec=self.name, meta={"parity": i >= p.n_data})
            for i, fr in enumerate(frames)
        ]
        self.manifest = Manifest(
            codec=self.name, data_len=len(data), n_units=len(chunks), n_oligos=len(oligos),
            params={"payload_bytes": self.layout.payload_bytes, "index_bytes": self.layout.index_bytes,
                    "rs_parity_pct": self.rs_parity_pct, "rs_k": p.k, "rs_r": p.r, "rs_blocks": p.n_blocks},
        )
        return oligos

    def _collect(self, oligos: list[Oligo], report: DecodeReport, strict: bool) -> dict[int, bytes]:
        payloads: dict[int, bytes] = {}
        for o in oligos:
            frame = self.nt_to_frame(self._strip_primers(o.sequence))
            if frame is None or len(frame) != self.layout.frame_bytes:
                report.undecodable += 1
                continue
            parsed = parse_frame(frame, self.layout)
            if not parsed.crc_ok:
                report.crc_failures += 1
                continue
            if parsed.index in payloads:
                if payloads[parsed.index] != parsed.payload:
                    report.conflicts += 1
                    if strict:
                        self.last_report = report
                        raise DuplicateConflictError(f"conflicting CRC-valid copies of index {parsed.index}")
                else:
                    report.duplicates += 1
                continue
            payloads[parsed.index] = parsed.payload
        report.accepted = len(payloads)
        return payloads

    def decode(self, oligos: list[Oligo], manifest: Manifest | None = None, best_effort: bool = False) -> bytes:
        report = DecodeReport(received=len(oligos))
        payloads = self._collect(oligos, report, strict=not best_effort)
        m = manifest or self.manifest
        if m is None:  # in-band path: no RS, length from frame 0
            self.last_report = report
            return assemble(payloads, self.layout)

        p = rs.plan(m.n_units, float(m.params.get("rs_parity_pct", 0)))
        report.ecc = f"reed-solomon k={p.k} r={p.r}" if p.r else "none"
        data, st = rs.decode(payloads, p, self.layout.payload_bytes)
        report.erasures, report.corrected_units = st.erasures, st.recovered_frames
        report.unrecoverable_units = st.unrecoverable_frames
        report.complete = not st.unrecoverable_frames
        self.last_report = report
        if st.unrecoverable_frames and not best_effort:
            raise MissingOligosError(st.unrecoverable_frames, m.n_units)
        zero = bytes(self.layout.payload_bytes)
        return chunks_to_data([d if d is not None else zero for d in data], m.data_len)


class FutureWorkCodec(Codec):
    status = CodecStatus.FUTURE_WORK

    def encode(self, data: bytes) -> list[Oligo]:
        raise NotImplementedError(f"{self.label} is listed as future work and is not implemented")

    def decode(self, oligos, manifest=None, best_effort=False) -> bytes:
        raise NotImplementedError(f"{self.label} is listed as future work and is not implemented")


# Illumina-style adapter fragments, used only when primers=True. Constant across oligos.
DEFAULT_FWD_PRIMER = "ACACGACGCTCTTCCGATCT"
DEFAULT_REV_PRIMER = "AGATCGGAAGAGCGGTTCAG"

# --------------------------------------------------------------------------- registry

_REGISTRY: dict[str, Callable[..., Codec]] = {}


def register_codec(cls):
    if cls.name in _REGISTRY:
        raise ValueError(f"codec {cls.name!r} registered twice")
    _REGISTRY[cls.name] = cls
    return cls


def get_codec(name: str, **kwargs) -> Codec:
    try:
        factory = _REGISTRY[name]
    except KeyError:
        raise KeyError(f"unknown codec {name!r}; available: {sorted(_REGISTRY)}") from None
    return factory(**kwargs)


def codec_class(name: str):
    return _REGISTRY[name]


def list_codecs() -> list[dict]:
    order = {CodecStatus.IMPLEMENTED: 0, CodecStatus.SIMPLIFIED: 1, CodecStatus.FUTURE_WORK: 2}
    return [c.info() for c in sorted(_REGISTRY.values(), key=lambda c: (order[c.status], c.name))]


def runnable_codecs() -> list[str]:
    return [c["name"] for c in list_codecs() if c["status"] != CodecStatus.FUTURE_WORK.value]
