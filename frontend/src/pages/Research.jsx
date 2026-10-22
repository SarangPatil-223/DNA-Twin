import { useEffect, useState } from "react";
import { get } from "@/lib/api";
import { ErrorNote, PageHead, StatusBadge } from "@/components/ui";

export default function ResearchPage() {
  const [r, setR] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    get("/research")
      .then(setR)
      .catch((e) => setErr(e.message));
  }, []);
  const status = (s) => (s.startsWith("implemented") ? "implemented" : s.startsWith("simplified") ? "simplified" : "future_work");
  return (
    <div>
      <PageHead title="What the literature says" lead={r?.headline} />
      <ErrorNote error={err} />
      {r && (
        <div className="space-y-10">
          <div className="overflow-x-auto rounded-xl border border-line bg-white">
            <table className="w-full min-w-[900px] text-left text-sm">
              <thead className="bg-paper text-xs text-soft">
                <tr>
                  <th className="px-3 py-2">Codec</th>
                  <th>Bits/nt</th>
                  <th>Error correction</th>
                  <th>Indels</th>
                  <th>Reported result</th>
                  <th>Compared with Church</th>
                  <th>Here</th>
                </tr>
              </thead>
              <tbody>
                {r.codecs.map((c) => (
                  <tr key={c.name} className="border-t border-line align-top">
                    <td className="px-3 py-2 font-bold">
                      <a href={c.source.url} target="_blank" rel="noreferrer">
                        {c.name}
                      </a>
                    </td>
                    <td className="py-2">{c.bits_per_nt}</td>
                    <td className="py-2">{c.ecc}</td>
                    <td className="py-2">{c.handles_indels}</td>
                    <td className="py-2 text-soft">{c.reported_result}</td>
                    <td className="py-2">{c.vs_church}</td>
                    <td className="py-2">
                      {c.platform_status === "not reviewed" ? (
                        <span className="text-xs text-soft">not reviewed</span>
                      ) : (
                        <StatusBadge status={status(c.platform_status)} />
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <section className="panel">
            <h2 className="text-2xl">
              <a href={r.benchmark_2026.url} target="_blank" rel="noreferrer" className="text-ink">
                The 2026 head-to-head benchmark
              </a>
            </h2>
            <p className="mt-1 text-sm text-soft">{r.benchmark_2026.title}</p>
            <ul className="mt-3 list-disc space-y-1 pl-5 text-sm">
              {r.benchmark_2026.findings.map((f) => (
                <li key={f}>{f}</li>
              ))}
            </ul>
          </section>
          <section>
            <h2 className="text-2xl">Tools that overlap with DNA Twin</h2>
            <div className="mt-3 grid gap-4 md:grid-cols-2">
              {r.related_platforms.map((p) => (
                <a
                  key={p.name}
                  href={p.url}
                  target="_blank"
                  rel="noreferrer"
                  className="panel block text-ink no-underline hover:border-ink"
                >
                  <p className="font-display text-base">{p.name}</p>
                  <p className="mt-1 text-sm text-soft">{p.what}</p>
                </a>
              ))}
            </div>
            <p className="mt-3 text-sm text-soft">
              What DNA Twin adds on top: measuring how much of the recovered data an LLM can still use, asking the same question
              through each codec, and image-specific storage modes with concealment.
            </p>
          </section>
          <p className="text-xs text-soft">
            Research notes updated {r.updated}. Figures are as reported by each source; the Gungnir paper could not be read and is
            listed by title only.
          </p>
        </div>
      )}
    </div>
  );
}
