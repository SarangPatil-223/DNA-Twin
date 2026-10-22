import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { get, post } from "@/lib/api";
import { pct } from "@/lib/format";
import { useWorkspace } from "@/lib/workspace";
import { NeedFile } from "@/components/NeedFile";
import { DiffLegend, SeqDiff } from "@/components/Seq";
import { Empty, ErrorNote, PageHead, SimBadge, Spinner, Stat, Term } from "@/components/ui";

const DEFAULT = { sub: 0.005, ins: 0.001, dele: 0.004, dropout: 0.01, years: 0, half_life_years: 500, copies: 5, seed: 42 };
function Slider({ id, label, tip, value, min, max, step, fmt, onChange }) {
  return (
    <div>
      <div className="flex justify-between text-sm">
        <label htmlFor={id} className="font-bold">
          <Term tip={tip}>{label}</Term>
        </label>
        <span className="tabular font-mono text-xs">{fmt(value)}</span>
      </div>
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(+e.target.value)}
        className="w-full accent-brand"
      />
    </div>
  );
}

export default function TwinPage() {
  const ws = useWorkspace();
  const navigate = useNavigate();
  const [p, setP] = useState(DEFAULT);
  const [presets, setPresets] = useState([]);
  const [sim, setSim] = useState(null);
  const [busy, setBusy] = useState(null);
  const [err, setErr] = useState(null);
  const [consensus, setConsensus] = useState("alignment");

  useEffect(() => {
    get("/settings")
      .then((s) => setPresets(s.channel_presets))
      .catch(() => {});
  }, []);
  useEffect(() => {
    if (ws.simulationId)
      get(`/simulation/${ws.simulationId}`)
        .then(setSim)
        .catch(() => {});
  }, [ws.simulationId]);

  const run = async () => {
    setBusy("Simulating");
    setErr(null);
    try {
      const s = await post("/simulation/run", { encoding_run_id: ws.encodingId, ...p });
      setSim(s);
      ws.set({ simulationId: s.id, retrievalId: null });
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(null);
    }
  };
  const retrieve = async () => {
    if (!sim) return;
    setBusy("Clustering, voting and decoding");
    setErr(null);
    try {
      const r = await post("/retrieval/run", { simulation_run_id: sim.id, consensus });
      ws.set({ retrievalId: r.id });
      navigate("/retrieval");
    } catch (e) {
      setErr(e.message);
      setBusy(null);
    }
  };
  const set = (k) => (v) => setP((x) => ({ ...x, [k]: v }));
  const total = p.sub + p.ins + p.dele;
  const survival = (1 - p.dropout) * Math.pow(0.5, p.years / p.half_life_years);
  const chart = (sim?.per_oligo_sample ?? [])
    .slice(0, 80)
    .map((o) => ({ i: o.i, subs: o.subs, ins: o.ins, dels: o.dels, dropped: o.dropped ? 1 : 0 }));

  if (ws.ready && !ws.encodingId)
    return (
      <NeedFile>
        <Empty title="Encode the file first" href="/encoding" cta="Go to encoding" />
      </NeedFile>
    );
  return (
    <NeedFile>
      <PageHead
        title="Digital twin"
        lead="Store the oligos for a while, then read them back with errors. Every rate is yours to set; the seed makes a run repeatable."
      />
      <div className="grid gap-6 lg:grid-cols-[360px_1fr]">
        <div className="panel h-fit space-y-4">
          {presets.length > 0 && (
            <div>
              <p className="label">Start from a preset</p>
              <div className="flex flex-wrap gap-2">
                {presets.map((pr) => (
                  <button
                    key={pr.name}
                    title={pr.note}
                    className="chip border-[1.5px] border-ink bg-white uppercase hover:bg-brand-tint"
                    onClick={() => setP((x) => ({ ...x, sub: pr.sub, ins: pr.ins, dele: pr.del }))}
                  >
                    {pr.name}
                  </button>
                ))}
              </div>
            </div>
          )}
          <Slider
            id="sub"
            label="Substitutions"
            tip="Chance per base that the read shows a different base (mostly sequencing)."
            value={p.sub}
            min={0}
            max={0.1}
            step={0.0005}
            fmt={(v) => pct(v, 2)}
            onChange={set("sub")}
          />
          <Slider
            id="ins"
            label="Insertions"
            tip="Chance per base that an extra random base appears."
            value={p.ins}
            min={0}
            max={0.05}
            step={0.0005}
            fmt={(v) => pct(v, 2)}
            onChange={set("ins")}
          />
          <Slider
            id="del"
            label="Deletions"
            tip="Chance per base that the base is missing (dominant in synthesis)."
            value={p.dele}
            min={0}
            max={0.05}
            step={0.0005}
            fmt={(v) => pct(v, 2)}
            onChange={set("dele")}
          />
          <Slider
            id="drop"
            label="Dropout"
            tip="Chance that an oligo species is lost entirely before sequencing."
            value={p.dropout}
            min={0}
            max={0.5}
            step={0.005}
            fmt={(v) => pct(v, 1)}
            onChange={set("dropout")}
          />
          <Slider
            id="years"
            label="Storage years"
            tip="Time in storage. Survival halves every half-life (a simple first-order decay you set)."
            value={p.years}
            min={0}
            max={5000}
            step={50}
            fmt={(v) => `${v} y`}
            onChange={set("years")}
          />
          <Slider
            id="hl"
            label="Half-life"
            tip="Assumed half-life of the stored DNA. This is a parameter, not a measured constant."
            value={p.half_life_years}
            min={50}
            max={10000}
            step={50}
            fmt={(v) => `${v} y`}
            onChange={set("half_life_years")}
          />
          <Slider
            id="cp"
            label="Read copies per oligo"
            tip="Sequencing reads per surviving oligo. More copies let consensus out-vote errors."
            value={p.copies}
            min={1}
            max={20}
            step={1}
            fmt={(v) => `${v}×`}
            onChange={set("copies")}
          />
          <label className="block font-mono text-[11px] uppercase tracking-[0.1em] text-soft">
            Seed
            <input type="number" className="field mt-1" value={p.seed} onChange={(e) => set("seed")(+e.target.value)} />
          </label>
          <p className="rounded-xl bg-paper p-3 text-xs text-soft">
            Total error {pct(total, 2)} per base, oligo survival {pct(survival)}.
          </p>
          <div className="flex gap-2">
            <button className="btn-primary flex-1" onClick={run} disabled={!!busy}>
              Run
            </button>
            <button
              className="btn-ghost"
              onClick={() => {
                setP(DEFAULT);
                setSim(null);
              }}
            >
              Reset
            </button>
          </div>
          {busy && <Spinner label={busy} />}
          <ErrorNote error={err} />
        </div>
        <div className="space-y-6">
          {!sim ? (
            <Empty title="No run yet">Set the channel on the left and press Run.</Empty>
          ) : (
            <>
              <section className="panel">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h3 className="text-xl">Run #{sim.id}</h3>
                  <SimBadge />
                </div>
                <div className="mt-4 grid grid-cols-2 gap-5 md:grid-cols-4">
                  <Stat label="Reads" value={sim.totals.reads.toLocaleString()} hint={`${sim.totals.species} oligo species`} />
                  <Stat label="Lost oligos" value={sim.totals.dropped} hint={pct(sim.totals.dropout_rate)} />
                  <Stat
                    label="Observed error"
                    value={pct(sim.totals.observed_error_rate, 2)}
                    hint={`${sim.totals.subs} sub, ${sim.totals.ins} ins, ${sim.totals.dels} del`}
                  />
                  <Stat label="Error-free reads" value={pct(sim.totals.error_free_reads / Math.max(1, sim.totals.reads))} />
                </div>
                <div className="mt-6 flex flex-wrap items-end gap-3">
                  <label className="font-mono text-[11px] uppercase tracking-[0.1em] text-soft">
                    Consensus
                    <select className="field mt-1 w-56" value={consensus} onChange={(e) => setConsensus(e.target.value)}>
                      <option value="alignment">Alignment (handles indels)</option>
                      <option value="majority">Majority (same-length reads)</option>
                    </select>
                  </label>
                  <button className="btn-brand" onClick={retrieve} disabled={!!busy}>
                    Get the file back
                  </button>
                </div>
              </section>
              <section className="panel">
                <h3 className="font-display text-base">Errors per oligo (first 80)</h3>
                <p className="text-xs text-soft">Summed over all read copies of each oligo. Lost oligos show a dropout bar.</p>
                <div className="mt-3 h-64">
                  <ResponsiveContainer>
                    <BarChart data={chart}>
                      <CartesianGrid vertical={false} stroke="#DEDBD2" />
                      <XAxis dataKey="i" tick={{ fontSize: 10 }} />
                      <YAxis tick={{ fontSize: 10 }} width={30} />
                      <Tooltip />
                      <Legend wrapperStyle={{ fontSize: 12 }} />
                      <Bar dataKey="subs" stackId="e" fill="#B8802F" name="substitutions" />
                      <Bar dataKey="ins" stackId="e" fill="#2E9E5B" name="insertions" />
                      <Bar dataKey="dels" stackId="e" fill="#C43D3D" name="deletions" />
                      <Bar dataKey="dropped" fill="#14171C" name="dropped" />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </section>
              <section className="panel space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h3 className="font-display text-base">Base-level diff of damaged reads</h3>
                  <DiffLegend />
                </div>
                {sim.diffs.length === 0 ? (
                  <p className="text-sm text-soft">No read had an error.</p>
                ) : (
                  sim.diffs.slice(0, 8).map((d, k) => (
                    <div key={k} className="rounded-xl bg-paper p-3">
                      <p className="mb-1 mono-label">
                        Oligo #{d.i}, {d.ops.length} edit{d.ops.length === 1 ? "" : "s"}
                      </p>
                      <SeqDiff original={d.original} read={d.read} ops={d.ops} />
                    </div>
                  ))
                )}
              </section>
            </>
          )}
        </div>
      </div>
    </NeedFile>
  );
}
