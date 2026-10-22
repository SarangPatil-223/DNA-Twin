# Algorithms

Status is honest by rule: *implemented* only if round-trip tests pass; *simplified* for reduced versions of a published scheme; *future work* for listed-only codecs, which raise `NotImplementedError`.

| Codec | Status | Mapping | Redundancy | Reference |
|---|---|---|---|---|
| Church | implemented | 1 bit/nt (A/C = 0, G/T = 1); free choice balances GC and caps runs at 3 | optional RS outer code | Church, Gao & Kosuri, *Science* 2012 |
| Raw 2-bit | implemented | 00→A … 11→T, no constraints; a density ceiling, not a published scheme | optional RS outer code | — |
| Yin-Yang | simplified | yang bit picks {A,T}/{C,G}, yin bit picks the base depending on the previous base; 16 XOR masks screened for GC 40–60 % and runs ≤ 4 | optional RS outer code | Ping et al., *Nat Comput Sci* 2022 |
| Goldman | simplified | 6 trits per byte (paper: Huffman 5–6), rotating code (no homopolymers), 100-trit fragments every 25 trits (4x), index + parity trit, alternate fragments reverse-complemented | 4x overlap, majority vote | Goldman et al., *Nature* 2013 |
| DNA Fountain | simplified | LT droplets (robust soliton), 2 bits/nt, screened for GC 45–55 % and runs ≤ 3; payload masked by a seed keystream; GF(2) elimination | droplet overhead (default 40 %) | Erlich & Zielinski, *Science* 2017 |
| HEDGES | future work | indel-correcting inner code | — | Press et al., *PNAS* 2020 |
| DNA-Aeon | future work | arithmetic-coding inner + Raptor outer | — | Welzel et al., *Nat Commun* 2023 |
| DP-DNA | future work | — | — | not reviewed |

## Detection vs correction

- **Detection**: CRC-16/CCITT per frame (frame codecs), parity trit (Goldman), CRC-16 per droplet (Fountain). A failed check turns the oligo into a known gap.
- **Correction**: Reed-Solomon over GF(256) across oligos (column-wise, blocks of ≤ 255), 4x voting (Goldman), GF(2) solving (Fountain), and consensus across read copies.

## Differences from the papers

- Grass et al. 2015 / DNA-RS use an inner RS code; here the inner layer is a CRC used only for detection.
- Goldman's first and last 25 trits are covered by a single fragment; in benchmarks this causes occasional failures at low error.
- Fountain keeps K in the manifest and masks droplet payloads with a seed keystream so small files pass screening.
