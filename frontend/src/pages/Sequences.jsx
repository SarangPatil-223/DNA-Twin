import { useEffect, useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { get, post, url } from "@/lib/api";
import { pct, statusTone } from "@/lib/format";
import { useWorkspace } from "@/lib/workspace";
import { Badge, Empty, ErrorNote, PageHead, SimBadge, Spinner } from "@/components/ui";
import { Seq } from "@/components/Seq";
import { NeedFile } from "@/components/NeedFile";

function stats(seq) {
  let gc = 0,
    run = 1,
    best = 1;
  for (let i = 0; i < seq.length; i++) {
    if (seq[i] === "G" || seq[i] === "C") gc++;
    if (i && seq[i] === seq[i - 1]) {
      run++;
      best = Math.max(best, run);
    } else run = 1;
  }
  return { gc: gc / seq.length, hp: best };
}

export default function SequencesPage() {
  const ws = useWorkspace();
  const [enc, setEnc] = useState(null);
  const [seqs, setSeqs] = useState([]);
  const [err, setErr] = useState(null);
  const [t, setT] = useState({ gcMin: 0.4, gcMax: 0.6, hp: 3 });
  const [val, setVal] = useState(null);
  const [busy, setBusy] = useState(false);
  const [q, setQ] = useState(0);

  useEffect(() => {
    if (!ws.encodingId) return;
    get(`/encoding/${ws.encodingId}`)
      .then(setEnc)
      .catch((e) => setErr(e.message));
    fetch(url(`/encoding/${ws.encodingId}/fasta`))
      .then((r) => r.text())
      .then((txt) => setSeqs(txt.split("\n").filter((l) => l && !l.startsWith(">"))))
      .catch(() => {});
  }, [ws.encodingId]);

  const per = useMemo(() => seqs.map(stats), [seqs]);
  const gcHist = useMemo(() => {
    const bins = Array.from({ length: 20 }, (_, i) => ({ bin: `${i * 5}`, count: 0 }));
    per.forEach((p) => bins[Math.min(19, Math.floor(p.gc * 20))].count++);
    return bins;
  }, [per]);
  const hpHist = useMemo(() => {
    const m = new Map();
    per.forEach((p) => m.set(p.hp, (m.get(p.hp) ?? 0) + 1));
    return [...m.entries()].sort((a, b) => a[0] - b[0]).map(([hp, count]) => ({ hp: String(hp), count }));
  }, [per]);

  const validate = async () => {
    if (!ws.encodingId) return;
    setBusy(true);
    setErr(null);
    try {
      setVal(
        await post("/validation/run", {
          encoding_run_id: ws.encodingId,
          thresholds: {
            gc_valid: [t.gcMin, t.gcMax],
            gc_warning: [Math.min(t.gcMin, 0.3), Math.max(t.gcMax, 0.7)],
            homopolymer_valid: t.hp,
            homopolymer_warning: Math.max(t.hp, 5),
          },
        }),
      );
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };

  if (ws.ready && !ws.encodingId)
    return (
      <NeedFile>
        <Empty title="Encode the file first" href="/encoding" cta="Go to encoding" />
      </NeedFile>
    );
  return (
    <NeedFile>
      <PageHead
        title="Sequence analysis"
        lead="GC balance and repeated-base runs across every oligo, checked against thresholds you set."
      >
        {enc && (
          <a className="btn-ghost no-underline" href={url(`/encoding/${enc.id}/fasta`)}>
            Download FASTA
          </a>
        )}
      </PageHead>
      <ErrorNote error={err} />
      {enc && (
        <div className="space-y-6">
          <p className="text-sm text-soft">
            Encoding #{enc.id} with <b>{enc.codec}</b>, {seqs.length.toLocaleString()} oligos loaded.{" "}
            <SimBadge className="ml-2" />
          </p>
          <div className="grid gap-6 md:grid-cols-2">
            <div className="panel">
              <h3 className="font-display text-base">GC content per oligo</h3>
              <p className="text-xs text-soft">Share of oligos in each 5% band. Most synthesis providers want 40–60%.</p>
              <div className="mt-3 h-56">
                <ResponsiveContainer>
                  <BarChart data={gcHist}>
                    <CartesianGrid vertical={false} stroke="#DEDBD2" />
                    <XAxis
                      dataKey="bin"
                      tick={{ fontSize: 11 }}
                      label={{ value: "GC %", position: "insideBottom", offset: -2, fontSize: 11 }}
                      height={32}
                    />
                    <YAxis tick={{ fontSize: 11 }} width={40} />
                    <Tooltip />
                    <Bar dataKey="count" fill="#2E9E5B" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
            <div className="panel">
              <h3 className="font-display text-base">Longest same-base run per oligo</h3>
              <p className="text-xs text-soft">Runs longer than 3–4 cause most synthesis and nanopore errors.</p>
              <div className="mt-3 h-56">
                <ResponsiveContainer>
                  <BarChart data={hpHist}>
                    <CartesianGrid vertical={false} stroke="#DEDBD2" />
                    <XAxis
                      dataKey="hp"
                      tick={{ fontSize: 11 }}
                      height={32}
                      label={{ value: "run length", position: "insideBottom", offset: -2, fontSize: 11 }}
                    />
                    <YAxis tick={{ fontSize: 11 }} width={40} />
                    <Tooltip />
                    <Bar dataKey="count" fill="#B8802F" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
          <div className="panel">
            <h3 className="font-display text-base">Validate against your thresholds</h3>
            <div className="mt-3 flex flex-wrap items-end gap-4">
              <label className="text-sm">
                GC min
                <input
                  type="number"
                  step={0.05}
                  min={0}
                  max={1}
                  className="field mt-1 w-24"
                  value={t.gcMin}
                  onChange={(e) => setT({ ...t, gcMin: +e.target.value })}
                />
              </label>
              <label className="text-sm">
                GC max
                <input
                  type="number"
                  step={0.05}
                  min={0}
                  max={1}
                  className="field mt-1 w-24"
                  value={t.gcMax}
                  onChange={(e) => setT({ ...t, gcMax: +e.target.value })}
                />
              </label>
              <label className="text-sm">
                Max run
                <input
                  type="number"
                  min={1}
                  max={10}
                  className="field mt-1 w-24"
                  value={t.hp}
                  onChange={(e) => setT({ ...t, hp: +e.target.value })}
                />
              </label>
              <button className="btn-primary" onClick={validate} disabled={busy}>
                {busy ? <Spinner label="Checking" /> : "Run validation"}
              </button>
            </div>
            {val && (
              <div className="mt-5 space-y-3">
                <div className="flex flex-wrap gap-2">
                  <Badge tone={statusTone(val.status)}>{val.status}</Badge>
                  {Object.entries(val.counts).map(([k, v]) => (
                    <Badge key={k} tone={statusTone(k)}>
                      {v} {k.toLowerCase()}
                    </Badge>
                  ))}
                </div>
                {val.worst.length > 0 ? (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-sm">
                      <thead className="text-xs text-soft">
                        <tr>
                          <th className="py-1">Oligo</th>
                          <th>Status</th>
                          <th>GC</th>
                          <th>Max run</th>
                          <th>Broken rule</th>
                        </tr>
                      </thead>
                      <tbody>
                        {val.worst.map((w) => (
                          <tr key={w.i} className="border-t border-line">
                            <td className="py-1.5 font-mono">#{w.i}</td>
                            <td>
                              <Badge tone={statusTone(w.status)}>{w.status}</Badge>
                            </td>
                            <td className="tabular">{pct(w.gc_content)}</td>
                            <td className="tabular">{w.max_homopolymer}</td>
                            <td className="text-soft">
                              {w.violations
                                .map(
                                  (v) =>
                                    `${v.constraint.replace("_", " ")} ${v.detail || v.value} (limit ${v.threshold}${v.position != null ? ` at ${v.position}` : ""})`,
                                )
                                .join("; ")}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="text-sm text-ok">Every oligo passes.</p>
                )}
              </div>
            )}
          </div>
          <div className="panel">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="font-display text-base">Oligo viewer</h3>
              <label className="text-sm">
                Oligo #
                <input
                  type="number"
                  min={0}
                  max={Math.max(0, seqs.length - 1)}
                  className="field ml-2 inline-block w-24"
                  value={q}
                  onChange={(e) => setQ(Math.max(0, Math.min(seqs.length - 1, +e.target.value)))}
                />
              </label>
            </div>
            {seqs[q] && (
              <div className="mt-3 rounded-xl bg-paper p-3">
                <Seq s={seqs[q]} max={2000} />
                <p className="mt-2 text-xs text-soft">
                  {seqs[q].length} nt, GC {pct(per[q]?.gc)}, longest run {per[q]?.hp}
                </p>
              </div>
            )}
          </div>
        </div>
      )}
    </NeedFile>
  );
}
