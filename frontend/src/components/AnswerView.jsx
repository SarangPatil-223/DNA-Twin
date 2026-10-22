import { ms } from "@/lib/format";
import { Badge } from "./ui";

export function AnswerView({ a }) {
  return (
    <div className="space-y-3">
      {a.lazy_retrieval && (
        <p className="text-xs text-soft">
          {a.lazy_retrieval.cached
            ? "Used cached recovery"
            : `Decoded from the virtual DNA store just now (${ms(a.lazy_retrieval.decode_ms)})`}
          , retrieval #{a.lazy_retrieval.retrieval_run_id}.
        </p>
      )}
      <div className="whitespace-pre-wrap text-[15px] leading-relaxed">{a.answer}</div>
      {a.warnings.map((w, i) => (
        <p key={i} className="rounded-lg bg-warnTint px-3 py-2 text-xs font-semibold text-warn">
          {w}
        </p>
      ))}
      {a.citations.length > 0 && (
        <details className="rounded-xl border border-line bg-paper p-3" open={a.citations.length <= 3}>
          <summary className="cursor-pointer mono-label">{a.citations.length} sources from recovered data</summary>
          <ul className="mt-2 space-y-2">
            {a.citations.map((c) => (
              <li key={c.tag} className="rounded-lg bg-white p-2 text-xs">
                <div className="mb-1 flex flex-wrap items-center gap-2">
                  <b>[{c.tag}]</b>
                  <span>
                    {c.source_file}
                    {c.page ? `, page ${c.page}` : ""}
                  </span>
                  <Badge tone="neutral">via {c.codec}</Badge>
                  {c.recovered_exact ? <Badge tone="ok">byte-exact</Badge> : <Badge tone="bad">possibly corrupted</Badge>}
                  <span className="text-soft">score {c.score.toFixed(3)}</span>
                </div>
                <p className="text-soft">
                  {c.snippet}
                  {c.snippet.length >= 400 ? "…" : ""}
                </p>
              </li>
            ))}
          </ul>
        </details>
      )}
      <p className="text-[11px] text-soft">Answered by {a.provider ?? "–"}. Simulation Result.</p>
    </div>
  );
}
