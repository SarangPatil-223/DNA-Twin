import { useEffect, useState } from "react";
import { get, post } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";
import { NeedFile } from "@/components/NeedFile";
import { AnswerView } from "@/components/AnswerView";
import { Badge, ErrorNote, PageHead, Spinner, Term } from "@/components/ui";

export default function AskPage() {
  const ws = useWorkspace();
  const [codecs, setCodecs] = useState([]);
  const [mode, setMode] = useState("codec");
  const [codec, setCodec] = useState("church");
  const [q, setQ] = useState("");
  const [turns, setTurns] = useState([]);
  const [docs, setDocs] = useState([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [provider, setProvider] = useState("");
  const [presets, setPresets] = useState([]);
  const [preset, setPreset] = useState("");

  const refresh = () =>
    get("/kb/documents")
      .then(setDocs)
      .catch(() => {});
  useEffect(() => {
    get("/codecs")
      .then((c) => setCodecs(c.filter((x) => x.status !== "future_work")))
      .catch(() => {});
    get("/settings")
      .then((s) => {
        setProvider(s.llm_provider);
        setPresets(s.channel_presets.map((p) => p.name));
        setPreset(s.channel_presets.find((p) => p.name.startsWith("Low"))?.name ?? "");
      })
      .catch(() => {});
    refresh();
  }, []);

  const ask = async (e) => {
    e.preventDefault();
    if (!q.trim() || !ws.file) return;
    setBusy(true);
    setErr(null);
    const question = q.trim();
    try {
      if (mode === "compare") {
        const res = await post("/kb/compare", {
          file_id: ws.file.id,
          question,
          codecs: codecs.map((c) => c.name),
          preset: preset || null,
        });
        setTurns((t) => [...t, { q: question, mode: `every codec, ${preset || "cached recoveries"}`, compare: res.results }]);
      } else if (mode === "codec") {
        const a = await post("/kb/query", { question, file_id: ws.file.id, codec });
        setTurns((t) => [...t, { q: question, mode: `via ${codec}`, answer: a }]);
      } else {
        const a = await post("/kb/query", { question });
        setTurns((t) => [...t, { q: question, mode: "all recovered documents", answer: a }]);
      }
      setQ("");
      refresh();
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <NeedFile>
      <PageHead
        title="Ask the recovered data"
        lead={
          <>
            Questions are answered only from text that came back out of simulated DNA — never from the upload. If the data for a
            codec isn't decoded yet, it is decoded on demand and cached. Answering with <b>{provider || "…"}</b>.
          </>
        }
      />
      <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
        <div className="space-y-5">
          <form onSubmit={ask} className="panel space-y-3">
            <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Where answers come from">
              {[
                ["codec", "One codec"],
                ["compare", "Every codec side by side"],
                ["all", "All recovered documents"],
              ].map(([k, l]) => (
                <button
                  type="button"
                  key={k}
                  role="radio"
                  aria-checked={mode === k}
                  onClick={() => setMode(k)}
                  className={`rounded-full border-[1.5px] px-4 py-1.5 font-mono text-[11px] uppercase tracking-[0.06em] ${mode === k ? "border-ink bg-ink text-paper" : "border-ink bg-transparent hover:bg-white"}`}
                >
                  {l}
                </button>
              ))}
              {mode === "compare" && (
                <select
                  aria-label="Storage conditions"
                  className="field w-auto py-1"
                  value={preset}
                  onChange={(e) => setPreset(e.target.value)}
                >
                  <option value="">Reuse existing recoveries</option>
                  {presets.map((p) => (
                    <option key={p} value={p}>
                      {p} channel, 3 reads
                    </option>
                  ))}
                </select>
              )}
              {mode === "codec" && (
                <select aria-label="Codec" className="field w-auto py-1" value={codec} onChange={(e) => setCodec(e.target.value)}>
                  {codecs.map((c) => (
                    <option key={c.name} value={c.name}>
                      {c.label}
                    </option>
                  ))}
                </select>
              )}
            </div>
            <div className="flex gap-2">
              <input
                className="field flex-1"
                placeholder={`Ask about ${ws.file?.filename ?? "your file"}…`}
                value={q}
                onChange={(e) => setQ(e.target.value)}
                aria-label="Question"
              />
              <button className="btn-primary" disabled={busy || !q.trim()}>
                Ask
              </button>
            </div>
            {busy && (
              <Spinner label={mode === "compare" ? "Decoding and answering through every codec" : "Retrieving and answering"} />
            )}
            <ErrorNote error={err} />
          </form>
          {turns.length === 0 && (
            <p className="text-sm text-soft">
              Try “every codec side by side” with a noisy channel: the same question can get different answers depending on what
              each code managed to bring back.
            </p>
          )}
          {[...turns].reverse().map((t, i) => (
            <article key={turns.length - i} className="panel space-y-4">
              <div>
                <p className="mono-label">{t.mode}</p>
                <p className="font-display text-lg">{t.q}</p>
              </div>
              {t.answer && <AnswerView a={t.answer} />}
              {t.compare && (
                <div className="grid gap-4 md:grid-cols-2">
                  {t.compare.map((c) => (
                    <div key={c.codec} className="rounded-xl border border-line p-4">
                      <div className="mb-2 flex flex-wrap items-center gap-2">
                        <b>{c.codec}</b>
                        {c.exact_match ? <Badge tone="ok">byte-exact</Badge> : <Badge tone="bad">damaged</Badge>}
                        {c.llm_readiness?.readiness != null && (
                          <Badge tone="neutral">LLM readiness {c.llm_readiness.readiness.toFixed(0)}</Badge>
                        )}
                      </div>
                      <AnswerView
                        a={{
                          answer: c.answer,
                          citations: c.citations,
                          warnings: c.warnings,
                          provider: c.provider,
                          label: "Simulation Result",
                          lazy_retrieval: c.lazy,
                        }}
                      />
                    </div>
                  ))}
                </div>
              )}
            </article>
          ))}
        </div>
        <aside className="panel h-fit">
          <h2 className="font-display text-base">
            <Term tip="Each document is the text recovered by one retrieval run. Its chunks remember which codec they came through and whether recovery was byte-exact.">
              Knowledge base
            </Term>
          </h2>
          {docs.length === 0 ? (
            <p className="mt-2 text-sm text-soft">
              Empty. Ask a question and the current file is decoded and added automatically.
            </p>
          ) : (
            <ul className="mt-3 space-y-2 text-sm">
              {docs.map((d) => (
                <li key={d.doc_id} className="rounded-xl bg-paper p-2">
                  <p className="truncate font-bold">{d.source_file}</p>
                  <p className="text-xs text-soft">
                    via {d.codec}, {d.chunks} chunk{d.chunks === 1 ? "" : "s"}, run #{d.retrieval_run_id}{" "}
                    {d.recovered_exact ? "" : "(damaged)"}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </aside>
      </div>
    </NeedFile>
  );
}
