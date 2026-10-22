import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { get, post } from "@/lib/api";
import { pct } from "@/lib/format";
import { useWorkspace } from "@/lib/workspace";
import { NeedFile } from "@/components/NeedFile";
import { RetrievalCard } from "@/components/RetrievalCard";
import { Badge, Empty, ErrorNote, PageHead, Spinner } from "@/components/ui";

export default function RetrievalPage() {
  const ws = useWorkspace();
  const [r, setR] = useState(null);
  const [hist, setHist] = useState([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  useEffect(() => {
    if (ws.retrievalId)
      get(`/retrieval/${ws.retrievalId}`)
        .then(setR)
        .catch((e) => setErr(e.message));
  }, [ws.retrievalId]);
  useEffect(() => {
    if (ws.file)
      get(`/retrievals?file_id=${ws.file.id}`)
        .then(setHist)
        .catch(() => {});
  }, [ws.file, r]);

  const run = async (consensus) => {
    if (!ws.simulationId) return;
    setBusy(true);
    setErr(null);
    try {
      const x = await post("/retrieval/run", { simulation_run_id: ws.simulationId, consensus });
      setR(x);
      ws.set({ retrievalId: x.id });
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <NeedFile>
      <PageHead
        title="Get it back"
        lead="Reads are grouped without knowing where they came from, voted into consensus, checked, corrected, and verified with SHA-256."
      >
        {ws.simulationId && (
          <div className="flex gap-2">
            <button className="btn-ghost" onClick={() => run("majority")} disabled={busy}>
              Retry with majority vote
            </button>
            <button className="btn-primary" onClick={() => run("alignment")} disabled={busy}>
              Retrieve latest run
            </button>
          </div>
        )}
      </PageHead>
      {busy && <Spinner label="Clustering, voting and decoding" />}
      <ErrorNote error={err} />
      {r ? (
        <div className="space-y-4">
          <RetrievalCard r={r} />
          <div className="flex flex-wrap gap-3">
            <Link to="/ask" className="btn-brand no-underline">
              Ask questions about this data
            </Link>
            <Link to="/compare" className="btn-ghost no-underline">
              Compare codecs
            </Link>
          </div>
        </div>
      ) : (
        !busy && (
          <Empty title="Nothing retrieved yet" href="/twin" cta="Run the digital twin">
            Simulate storage and reading first, then come back.
          </Empty>
        )
      )}
      {hist.length > 1 && (
        <section className="mt-10">
          <h2 className="mb-3 text-2xl">Earlier retrievals of this file</h2>
          <div className="overflow-x-auto rounded-xl border border-line bg-white">
            <table className="w-full text-left text-sm">
              <thead className="bg-paper text-xs text-soft">
                <tr>
                  <th className="px-3 py-2">Run</th>
                  <th>Codec</th>
                  <th>Channel error</th>
                  <th>Copies</th>
                  <th>Result</th>
                  <th>Byte accuracy</th>
                  <th>LLM readiness</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {hist.map((h) => (
                  <tr key={h.id} className="border-t border-line">
                    <td className="px-3 py-2 font-mono">#{h.id}</td>
                    <td>{h.codec}</td>
                    <td className="tabular">{pct((h.channel?.sub ?? 0) + (h.channel?.ins ?? 0) + (h.channel?.dele ?? 0), 2)}</td>
                    <td className="tabular">{h.channel?.copies}×</td>
                    <td>{h.exact_match ? <Badge tone="ok">exact</Badge> : <Badge tone="bad">damaged</Badge>}</td>
                    <td className="tabular">{pct(h.metrics.file_byte_accuracy, 2)}</td>
                    <td className="tabular">{h.llm_readiness?.readiness != null ? h.llm_readiness.readiness.toFixed(0) : "–"}</td>
                    <td>
                      <button
                        className="text-sm font-bold text-brand-deep underline"
                        onClick={() => {
                          setR(h);
                          ws.set({ retrievalId: h.id });
                        }}
                      >
                        Open
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </NeedFile>
  );
}
