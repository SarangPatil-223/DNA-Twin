"""End-to-end orchestration: file -> container -> codec -> channel -> clustering/consensus -> decode -> verify.

Pure Python; the API and the benchmark both call these functions.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from . import SIMULATION_LABEL
from .binary import ContainerError, pack_container, read_header, unpack_container
from .channel import ChannelParams, ChannelResult, simulate
from .codec_base import Codec, Manifest, get_codec
from .constraints import ConstraintThresholds
from .ecc.consensus import cluster_reads, consensus_all, key_distance_for
from .metrics import bit_accuracy, byte_accuracy, payload_slice, sequence_stats
from .oligo import FramingError, Oligo

def _ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 2)

@dataclass
class EncodeResult:
    codec_name: str
    codec_params: dict
    container: bytes
    oligos: list[Oligo]
    manifest: Manifest
    constraints: dict
    stats: dict
    encode_ms: float

    @property
    def sequences(self) -> list[str]:
        return [o.sequence for o in self.oligos]

@dataclass
class RetrievalResult:
    recovered_container: bytes
    recovered_file: bytes | None
    exact_match: bool
    sha256_expected: str
    sha256_got: str | None
    decode_report: dict
    cluster_stats: dict
    metrics: dict
    notes: list[str] = field(default_factory=list)
    lost_ranges: list[tuple[int, int]] = field(default_factory=list)  # container byte ranges zero-filled
    label: str = SIMULATION_LABEL

def encode_file(data: bytes, filename: str, mime: str, codec_name: str, codec_params: dict | None = None,
                compress: bool = False, thresholds: ConstraintThresholds | None = None) -> EncodeResult:
    params = dict(codec_params or {})
    codec = get_codec(codec_name, **params)
    t0 = time.perf_counter()
    container = pack_container(data, filename, mime, codec_name, compress=compress)
    oligos = codec.encode(container)
    ms = _ms(t0)
    seqs = [o.sequence for o in oligos]
    st = sequence_stats(seqs)
    file_bits = 8 * len(data)
    f, r = codec.primer_lengths()
    coded_nt = st["total_nt"] - len(seqs) * (f + r)
    st.update({
        "file_bytes": len(data),
        "file_bits": file_bits,
        "container_bytes": len(container),
        "density_bits_per_nt": file_bits / st["total_nt"] if st["total_nt"] else 0.0,
        "coded_density_bits_per_nt": file_bits / coded_nt if coded_nt else 0.0,
        "overhead_vs_2bit": (st["total_nt"] / (file_bits / 2)) if file_bits else None,
        "nominal_bits_per_nt": codec.nominal_bits_per_nt,
        "primer_nt_per_oligo": f + r,
    })
    rep = codec.constraints_satisfied(oligos, thresholds)
    return EncodeResult(codec_name, params, container, oligos, codec.manifest, rep.to_dict(), st, ms)

def run_channel(sequences: list[str], params: ChannelParams) -> tuple[ChannelResult, float]:
    t0 = time.perf_counter()
    res = simulate(sequences, params)
    return res, _ms(t0)

def retrieve(codec_name: str, codec_params: dict, manifest: Manifest, reads: list[str], original_container: bytes,
             original_data: bytes, consensus: str = "alignment", assumed_error_rate: float = 0.0,
             expected_len: int | None = None) -> RetrievalResult:
    codec: Codec = get_codec(codec_name, **(codec_params or {}))
    notes: list[str] = []
    t0 = time.perf_counter()
    key_dist = key_distance_for(assumed_error_rate)
    clusters, cst = cluster_reads(reads, max_key_dist=key_dist, trim=codec.primer_lengths())
    t_cluster = _ms(t0)
    t1 = time.perf_counter()
    seqs = consensus_all(clusters, consensus, expected_len)
    t_cons = _ms(t1)
    t2 = time.perf_counter()
    try:
        recovered = codec.decode([Oligo(i, s, codec_name) for i, s in enumerate(seqs)], manifest, best_effort=True)
    except (FramingError, ValueError) as exc:
        notes.append(f"decoder failed: {exc}")
        recovered = bytes(len(original_container))
    t_dec = _ms(t2)

    recovered_file = None
    sha_got = None
    exact = False
    try:
        up = unpack_container(recovered)
        recovered_file, sha_got, exact = up.data, up.sha256_got, up.sha256_ok
    except ContainerError as exc:
        notes.append(f"container unreadable: {exc}")

    meta, _, _ = read_header(original_container)
    partial = payload_slice(original_container, recovered)
    if recovered_file is None and partial is not None:
        recovered_file = partial  # best-effort bytes for partial metrics and image/text previews
        notes.append("file bytes taken from the damaged container using the original header length")
    file_ref = partial if (partial is not None and not exact) else recovered_file

    rep = codec.last_report.to_dict()
    metrics = {
        "exact_match": exact,
        "container_byte_accuracy": byte_accuracy(original_container, recovered),
        "container_bit_accuracy": bit_accuracy(original_container, recovered),
        "file_byte_accuracy": 1.0 if exact else byte_accuracy(original_data, file_ref),
        "file_bit_accuracy": 1.0 if exact else bit_accuracy(original_data, file_ref),
        "size_diff_bytes": (len(recovered_file) - len(original_data)) if recovered_file is not None else None,
        "units_unrecoverable": rep.get("n_unrecoverable", 0),
        "crc_failures": rep["crc_failures"],
        "undecodable": rep["undecodable"],
        "erasures": rep["erasures"],
        "corrected_units": rep["corrected_units"],
        "cluster_ms": t_cluster,
        "consensus_ms": t_cons,
        "decode_ms": t_dec,
        "retrieval_ms": round(t_cluster + t_cons + t_dec, 2),
        "clusters": cst.clusters,
        "compressed": meta.compressed,
    }
    lost = codec.lost_byte_ranges(manifest)
    metrics["bytes_zero_filled"] = sum(b - a for a, b in lost)
    return RetrievalResult(recovered, recovered_file, exact, meta.sha256, sha_got, rep, cst.to_dict(), metrics, notes, lost)

def run_all(data: bytes, filename: str, mime: str, codec_name: str, channel: ChannelParams,
            codec_params: dict | None = None, compress: bool = False, consensus: str = "alignment") -> dict:
    enc = encode_file(data, filename, mime, codec_name, codec_params, compress)
    ch, sim_ms = run_channel(enc.sequences, channel)
    ret = retrieve(codec_name, enc.codec_params, enc.manifest, ch.reads, enc.container, data, consensus,
                   channel.total_error_rate, len(enc.oligos[0].sequence) if enc.oligos else None)
    return {"label": SIMULATION_LABEL, "encode": enc, "channel": ch, "sim_ms": sim_ms, "retrieval": ret}
