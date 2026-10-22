import { bytes, ms, num, pct, statusTone } from "@/lib/format";
import { Badge, SimBadge, Stat, Term } from "./ui";
import { Seq } from "./Seq";

export function EncodingSummary({ e, oligos = 6 }) {
  const s = e.stats;
  const c = e.constraints;
  return (
    <section className="panel space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-xl">
          Encoding #{e.id}: {e.codec}
          {e.params.rs_parity_pct ? ` + ${e.params.rs_parity_pct}% RS parity` : ""}
        </h3>
        <SimBadge />
      </div>
      <div className="grid grid-cols-2 gap-5 md:grid-cols-4">
        <Stat label="Oligos" value={s.n_oligos.toLocaleString()} hint={`${s.oligo_len} nt each`} />
        <Stat label="Nucleotides" value={s.total_nt.toLocaleString()} hint={`for ${bytes(s.file_bytes)}`} />
        <Stat
          label={"Density"}
          value={`${num(s.density_bits_per_nt, 3)}`}
          hint={`bits/nt, nominal ${num(s.nominal_bits_per_nt, 2)}`}
        />
        <Stat label="Encode time" value={ms(e.encode_ms)} />
      </div>
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-bold">Constraints</span>
        <Badge tone={statusTone(c.status)}>{c.status}</Badge>
        <span className="text-soft">
          GC {pct(c.mean_gc)}, max{" "}
          <Term tip="The longest run of the same base, like AAAA. Long runs cause synthesis and sequencing errors.">
            homopolymer
          </Term>{" "}
          {c.max_homopolymer}
        </span>
        {Object.entries(c.counts).map(([k, v]) => (
          <Badge key={k} tone={statusTone(k)}>
            {v} {k.toLowerCase()}
          </Badge>
        ))}
      </div>
      {Object.keys(c.violation_counts).length > 0 && (
        <p className="text-sm text-soft">
          Sequences breaking a rule:{" "}
          {Object.entries(c.violation_counts)
            .map(([k, v]) => `${k.replace("_", " ")} ${v}`)
            .join(", ")}
        </p>
      )}
      {e.sample_oligos && (
        <div className="space-y-2">
          <p className="mono-label">First oligos</p>
          {e.sample_oligos.slice(0, oligos).map((o, i) => (
            <div key={i} className="rounded-xl bg-paper px-3 py-2">
              <Seq s={o} />
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
