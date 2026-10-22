import { useEffect, useState } from "react";
import { post, url } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";
import { NeedFile } from "@/components/NeedFile";
import { ErrorNote, PageHead, ScorePill, SimBadge, Spinner } from "@/components/ui";

const PROFILES = [
  ["balanced", "Balanced", "Recovery, tolerance, density, constraints, LLM use and speed weighed evenly."],
  ["archival", "Long-term archive", "Getting every byte back matters most; density second."],
  ["llm_rag", "LLM / RAG", "Recovered text must stay usable for retrieval and answers; decode speed matters."],
  ["cost_density", "Cost and density", "Fewest nucleotides per byte, as long as the file still comes back."],
];

export default function RecommendPage() {
  const ws = useWorkspace();
  const [profile, setProfile] = useState("balanced");
  const [rec, setRec] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  const run = async (p = profile) => {
    if (!ws.file) return;
    setBusy(true);
    setErr(null);
    try {
      setRec(await post("/recommendation/run", { file_id: ws.file.id, profile: p }));
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };
  useEffect(() => {
    if (ws.file) run();
  }, [ws.file?.id]);

  return (
    <NeedFile>
      <PageHead
        title="Which codec should you use?"
        lead="A transparent weighted score over measured results. Every reason quotes the number behind it. If this file has no benchmark yet, a short one runs first."
      >
        <a
          className="btn-ghost no-underline"
          href={url("/recommendation/dataset.csv")}
          title="All benchmark results as a labelled table for training a model"
        >
          Download simulated dataset
        </a>
      </PageHead>
      <div className="grid gap-3 md:grid-cols-4" role="radiogroup" aria-label="What matters to you">
        {PROFILES.map(([k, t, d]) => (
          <button
            key={k}
            role="radio"
            aria-checked={profile === k}
            onClick={() => {
              setProfile(k);
              run(k);
            }}
            disabled={busy}
            className={`rounded-xl border-[1.5px] p-4 text-left ${profile === k ? "border-ink bg-brand-tint" : "border-ink/25 bg-white hover:border-ink"}`}
          >
            <p className="font-display text-base">{t}</p>
            <p className="mt-1 text-xs text-soft">{d}</p>
          </button>
        ))}
      </div>
      <div className="mt-4">
        {busy && <Spinner label="Scoring (a first benchmark can take a minute)" />}
        <ErrorNote error={err} />
      </div>
      {rec && rec.ranking.length > 0 && (
        <div className="mt-6 space-y-5">
          <div className="overflow-hidden rounded-xl border-[1.5px] border-ink bg-white">
            <div className="flex items-center justify-between border-b-[1.5px] border-ink bg-brand-tint px-5 py-3">
              <span className="font-display text-sm">Recommendation</span>
              <SimBadge />
            </div>
            <div className="p-5">
              <p className="text-lg font-semibold leading-snug">{rec.headline}</p>
              <p className="mt-2 font-mono text-[12px] leading-relaxed text-soft">
                {rec.caveat} Benchmark #{rec.benchmark_id}.
              </p>
            </div>
          </div>
          <ol className="space-y-3">
            {rec.ranking.map((r, i) => (
              <li key={r.variant} className="rounded-xl border-[1.5px] border-ink bg-white p-5">
                <div className="flex flex-wrap items-center justify-between gap-4">
                  <div className="flex items-center gap-4">
                    <span className="tabular font-display text-4xl text-soft/40">{i + 1}</span>
                    <div>
                      <p className="font-display text-lg">{r.variant}</p>
                      <p className="text-sm text-soft">
                        {r.strengths.length ? `Strong on ${r.strengths.join(" and ")}` : "No standout strength in this sweep"}
                        {r.weaknesses.length ? `. Weak on ${r.weaknesses.join(", ")}` : ""}.
                      </p>
                    </div>
                  </div>
                  <ScorePill score={r.score} label="Fit score" />
                </div>
                <details className="mt-3">
                  <summary className="cursor-pointer text-sm font-bold text-brand-deep">Why this score</summary>
                  <div className="mt-2 overflow-x-auto">
                    <table className="w-full text-left text-sm">
                      <thead className="text-xs text-soft">
                        <tr>
                          <th className="py-1">Metric</th>
                          <th>Weight</th>
                          <th>Measured</th>
                          <th>Points</th>
                          <th>Compared with</th>
                        </tr>
                      </thead>
                      <tbody>
                        {r.reasons.map((x) => (
                          <tr key={x.metric} className="border-t border-line">
                            <td className="py-1.5 font-semibold">{x.metric}</td>
                            <td className="tabular">{Math.round(x.weight * 100)}%</td>
                            <td>{x.value}</td>
                            <td className="tabular">{x.points.toFixed(1)}</td>
                            <td className="text-soft">{x.comparison}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </details>
              </li>
            ))}
          </ol>
        </div>
      )}
    </NeedFile>
  );
}
