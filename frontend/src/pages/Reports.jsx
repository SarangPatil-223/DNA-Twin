import { useState } from "react";
import { url } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";
import { NeedFile } from "@/components/NeedFile";
import { ErrorNote, PageHead, Spinner } from "@/components/ui";

export default function ReportsPage() {
  const ws = useWorkspace();
  const [profile, setProfile] = useState("balanced");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const gen = async () => {
    if (!ws.file) return;
    setBusy(true);
    setErr(null);
    try {
      const r = await fetch(url("/reports/generate"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ file_id: ws.file.id, profile }),
      });
      if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
      const blob = await r.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `dna_twin_report_${ws.file.filename.replace(/\.[^.]+$/, "")}.pdf`;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <NeedFile>
      <PageHead
        title="Reports"
        lead="A PDF with the recommendation, benchmark charts, every retrieval run for this file, the literature comparison and the limitations. Each page is marked Simulation Result."
      />
      <div className="panel flex flex-wrap items-end gap-4">
        <p className="w-full text-sm">
          File: <b>{ws.file?.filename}</b>
        </p>
        <label className="font-mono text-[11px] uppercase tracking-[0.1em] text-soft">
          Recommendation profile
          <select className="field mt-1 w-56" value={profile} onChange={(e) => setProfile(e.target.value)}>
            <option value="balanced">Balanced</option>
            <option value="archival">Long-term archive</option>
            <option value="llm_rag">LLM / RAG</option>
            <option value="cost_density">Cost and density</option>
          </select>
        </label>
        <button className="btn-primary" onClick={gen} disabled={busy}>
          {busy ? <Spinner label="Building PDF" /> : "Download PDF report"}
        </button>
        <ErrorNote error={err} />
      </div>
      <p className="mt-4 text-sm text-soft">
        Run a benchmark on the Compare page first for charts and a recommendation; otherwise the report lists retrieval runs and
        research only.
      </p>
    </NeedFile>
  );
}
