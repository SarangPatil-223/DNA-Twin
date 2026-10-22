"""Published codecs listed for comparison but not implemented. Calling them raises NotImplementedError."""

from ..codec_base import FutureWorkCodec, register_codec


@register_codec
class HedgesCodec(FutureWorkCodec):
    name = "hedges"
    label = "HEDGES 2020"
    description = "Hash-based inner code that corrects insertions and deletions in a single read."
    reference = "Press et al. HEDGES error-correcting code for DNA storage corrects indels and allows sequence constraints. PNAS 2020."


@register_codec
class DnaAeonCodec(FutureWorkCodec):
    name = "dna_aeon"
    label = "DNA-Aeon 2023"
    description = "Arithmetic-coding inner code with constraints + Raptor fountain outer code."
    reference = "Welzel et al. DNA-Aeon provides flexible arithmetic coding for constraint adherence and error correction in DNA storage. Nat Commun 2023."


@register_codec
class DpDnaCodec(FutureWorkCodec):
    name = "dp_dna"
    label = "DP-DNA"
    description = "Dynamic-programming constrained coding. Listed for completeness only."
    reference = "Not reviewed in this platform's research notes."
