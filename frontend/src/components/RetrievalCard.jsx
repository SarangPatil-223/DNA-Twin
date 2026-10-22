import { url } from "@/lib/api";
import { ms, num, pct } from "@/lib/format";
import { Badge, SimBadge, Stat, Term } from "./ui";

export function ImageStrip({ r }) {
  const im = r.image_metrics;
  if (!im) return null;
  const tiles = [
    ["ref", "Original", "reference pixels"],
    [
      "img",
      "Recovered",
      im.raw.decodable
        ? `SSIM ${num(im.raw.ssim, 3)}, PSNR ${im.raw.psnr_infinite ? "∞" : num(im.raw.psnr_db, 1) + " dB"}`
        : "could not be decoded",
    ],
    [
      "conceal",
      "After concealment",
      im.concealed.decodable
        ? `SSIM ${num(im.concealed.ssim, 3)}, PSNR ${im.concealed.psnr_infinite ? "∞" : num(im.concealed.psnr_db, 1) + " dB"}`
        : "–",
    ],
    ["diff", "Error heatmap", im.lost_pixel_share != null ? `${pct(im.lost_pixel_share)} pixels zero-filled` : ""],
  ];
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      {tiles.map(([k, t, sub]) => (
        <figure key={k} className="rounded-xl border border-line bg-paper p-2">
          <img
            src={url(`/retrieval/${r.id}/image/${k}`)}
            alt={`${t} for run ${r.id}`}
            className="aspect-[3/2] w-full rounded-lg bg-white object-contain [image-rendering:pixelated]"
            onError={(e) => (e.target.style.visibility = "hidden")}
          />
          <figcaption className="mt-1 text-xs">
            <b>{t}</b>
            <br />
            <span className="text-soft">{sub}</span>
          </figcaption>
        </figure>
      ))}
    </div>
  );
}

export function RetrievalCard({ r }) {
  const m = r.metrics;
  const d = r.decode_report;
  const llm = r.llm_readiness;
  return (
    <section className="panel space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <span
            className={`rounded-xl px-4 py-2 font-display text-2xl ${r.exact_match ? "bg-okTint text-ok" : "bg-badTint text-bad"}`}
          >
            {r.exact_match ? "Byte-exact" : "Not exact"}
          </span>
          <div>
            <p className="font-bold">
              Retrieval #{r.id} via {r.codec}
            </p>
            <p className="text-xs text-soft">
              {r.consensus} consensus
              {r.channel
                ? `, ${r.channel.copies}× reads, ${pct((r.channel.sub ?? 0) + (r.channel.ins ?? 0) + (r.channel.dele ?? 0), 2)} error`
                : ""}
            </p>
          </div>
        </div>
        <SimBadge />
      </div>
      <div className="grid gap-1 rounded-xl bg-paper p-3 font-mono text-[11px]">
        <p>
          <span className="inline-block w-20 font-body font-bold text-soft">Expected</span>
          {r.sha256_expected}
        </p>
        <p>
          <span className="inline-block w-20 font-body font-bold text-soft">Recovered</span>
          <span className={r.exact_match ? "text-ok" : "text-bad"}>{r.sha256_got ?? "container unreadable"}</span>
        </p>
      </div>
      <div className="grid grid-cols-2 gap-5 md:grid-cols-4">
        <Stat label="File byte accuracy" value={pct(m.file_byte_accuracy, 2)} />
        <Stat label="Bit accuracy" value={pct(m.file_bit_accuracy, 3)} />
        <Stat label="Retrieval time" value={ms(m.retrieval_ms)} hint={`cluster ${ms(m.cluster_ms)}, decode ${ms(m.decode_ms)}`} />
        <Stat label="Clusters" value={m.clusters} hint={`${r.cluster_stats.merged_reads ?? 0} reads merged by distance`} />
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <div className="rounded-xl border border-line p-4">
          <p className="font-display text-sm">
            <Term tip="Finds damaged oligos but cannot repair them. A CRC-16 per oligo (or Goldman's parity trit) rejects bad reads so they become known gaps.">
              Error detection
            </Term>
          </p>
          <ul className="mt-2 space-y-1 text-sm">
            <li>
              Consensus sequences received: <b className="tabular">{d.received}</b>
            </li>
            <li>
              Rejected by checksum: <b className="tabular">{d.crc_failures}</b>
            </li>
            <li>
              Could not be mapped back to bytes: <b className="tabular">{d.undecodable}</b>
            </li>
            <li>
              Duplicate copies ignored: <b className="tabular">{d.duplicates}</b>
            </li>
          </ul>
        </div>
        <div className="rounded-xl border border-line p-4">
          <p className="font-display text-sm">
            <Term tip="Repairs data. Reed-Solomon rebuilds missing oligos from parity; Goldman votes across 4 overlapping copies; fountain codes solve for missing segments.">
              Error correction
            </Term>
          </p>
          <ul className="mt-2 space-y-1 text-sm">
            <li>
              Method: <b>{d.ecc}</b>
            </li>
            <li>
              Gaps before correction: <b className="tabular">{d.erasures}</b>
            </li>
            <li>
              Units repaired: <b className="tabular">{d.corrected_units}</b>
            </li>
            <li>
              Units still missing: <b className={`tabular ${d.n_unrecoverable ? "text-bad" : "text-ok"}`}>{d.n_unrecoverable}</b>
            </li>
          </ul>
        </div>
      </div>
      {llm && (
        <div className="rounded-xl border border-line p-4">
          <p className="font-display text-sm">
            <Term tip="How usable the recovered data is for an LLM: text similarity to the original, share of chunks intact, and whether retrieval returns the same chunks. 100 = identical.">
              LLM readiness
            </Term>{" "}
            {llm.readiness != null ? (
              <span className="tabular">{llm.readiness.toFixed(0)}/100</span>
            ) : (
              <span className="text-soft">not measured</span>
            )}
          </p>
          {llm.readiness != null ? (
            <p className="mt-1 text-sm text-soft">
              Text similarity {pct(llm.text_similarity)}
              {llm.chunk_intact != null && (
                <>
                  , chunks intact {pct(llm.chunk_intact)}, retrieval overlap {pct(llm.retrieval_overlap)}
                </>
              )}
              {llm.source ? ` (${llm.source})` : ""}
            </p>
          ) : (
            <p className="mt-1 text-sm text-soft">{llm.reason}</p>
          )}
        </div>
      )}
      <ImageStrip r={r} />
      {r.notes.length > 0 && (
        <ul className="space-y-1 text-xs text-soft">
          {r.notes.map((n, i) => (
            <li key={i}>Note: {n}</li>
          ))}
        </ul>
      )}
      <div className="flex flex-wrap gap-3">
        {r.downloadable && (
          <a className="btn-primary no-underline" href={url(`/retrieval/${r.id}/download`)}>
            Download recovered file
          </a>
        )}
        {!r.exact_match && <Badge tone="bad">Damaged: downloaded bytes differ from the original</Badge>}
      </div>
    </section>
  );
}
