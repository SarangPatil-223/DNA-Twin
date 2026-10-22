import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { get, post, url } from "@/lib/api";
import { ms, num, pct, statusTone } from "@/lib/format";
import { useWorkspace } from "@/lib/workspace";
import { NeedFile } from "@/components/NeedFile";
import { MetricChart, variantsOf } from "@/components/BenchCharts";
import { Badge, Empty, ErrorNote, PageHead, SimBadge, Spinner, Term } from "@/components/ui";

const RATES = [0, 0.005, 0.01, 0.02, 0.03, 0.05, 0.08, 0.1];

export default function ComparePage() {
  const ws = useWorkspace();
  const [codecs, setCodecs] = useState([]);
  const [chosen, setChosen] = useState([]);
  const [rates, setRates] = useState([0, 0.005, 0.01, 0.02, 0.03, 0.05]);
  const [rsOn, setRsOn] = useState(true);
  const [seeds, setSeeds] = useState(2);
  const [copies, setCopies] = useState(5);
  const [dropout, setDropout] = useState(0.02);
  const [bench, setBench] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  useEffect(() => {
    get("/codecs")
      .then((c) => {
        setCodecs(c);
        setChosen(c.filter((x) => x.status !== "future_work").map((x) => x.name));
      })
      .catch((e) => setErr(e.message));
  }, []);
  useEffect(() => {
    if (ws.file)
      get(`/benchmark/latest/${ws.file.id}`)
        .then(setBench)
        .catch(() => setBench(null));
  }, [ws.file]);

  const nRuns = useMemo(() => {
    const variants = chosen.reduce((a, c) => a + (codecs.find((x) => x.name === c)?.supports_rs && rsOn ? 2 : 1), 0);
    return variants * rates.length * seeds;
  }, [chosen, codecs, rates, seeds, rsOn]);

  const run = async () => {
    if (!ws.file) return;
    setBusy(true);
    setErr(null);
    try {
      setBench(
        await post("/benchmark/run", {
          file_id: ws.file.id,
          codecs: chosen,
          error_rates: rates,
          rs_levels: rsOn ? [0, 30] : [0],
          seeds,
          copies,
          dropout,
        }),
      );
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };

  const perVariant = useMemo(() => {
    if (!bench) return [];
    return variantsOf(bench.summary)
      .map((v) => {
        const rs = bench.summary.filter((r) => r.variant === v);
        const llm = rs.map((r) => r.llm_readiness_mean).filter((x) => x != null);
        return {
          v,
          first: rs[0],
          survival: rs.reduce((a, r) => a + r.exact_match_mean, 0) / rs.length,
          llm: llm.length ? llm.reduce((a, b) => a + b, 0) / llm.length : null,
          rt: rs.reduce((a, r) => a + (r.retrieval_ms_mean ?? 0), 0) / rs.length,
        };
      })
      .sort((a, b) => b.survival - a.survival);
  }, [bench]);
  const hasLLM = bench?.summary.some((r) => r.llm_readiness_mean != null);

  return (
    <NeedFile>
      <PageHead
        title="Compare codecs"
        lead={
          <>
            Run every codec on <b>{ws.file?.filename}</b> across error rates and seeds. Recovery counts only when SHA-256 matches.
          </>
        }
      />
      <div className="panel space-y-5">
        <div>
          <p className="label">Codecs</p>
          <div className="flex flex-wrap gap-2">
            {codecs
              .filter((c) => c.status !== "future_work")
              .map((c) => {
                const on = chosen.includes(c.name);
                return (
                  <button
                    key={c.name}
                    aria-pressed={on}
                    onClick={() => setChosen(on ? chosen.filter((x) => x !== c.name) : [...chosen, c.name])}
                    className={`rounded-full border-[1.5px] px-4 py-1.5 font-mono text-[11px] uppercase tracking-[0.06em] ${on ? "border-ink bg-ink text-paper" : "border-ink bg-transparent hover:bg-white"}`}
                  >
                    {c.label}
                  </button>
                );
              })}
          </div>
        </div>
        <div>
          <p className="label">Error rates (total per base, split 50% sub, 10% ins, 40% del)</p>
          <div className="flex flex-wrap gap-2">
            {RATES.map((r) => {
              const on = rates.includes(r);
              return (
                <button
                  key={r}
                  aria-pressed={on}
                  onClick={() => setRates(on ? rates.filter((x) => x !== r) : [...rates, r].sort((a, b) => a - b))}
                  className={`rounded-full border-[1.5px] px-3 py-1.5 font-mono text-[11px] ${on ? "border-brand bg-brand text-white" : "border-ink bg-transparent hover:bg-white"}`}
                >
                  {pct(r, 1)}
                </button>
              );
            })}
          </div>
        </div>
        <div className="flex flex-wrap items-end gap-5">
          <label className="font-mono text-[11px] uppercase tracking-[0.1em] text-soft">
            Seeds
            <input
              type="number"
              min={1}
              max={10}
              className="field mt-1 w-20"
              value={seeds}
              onChange={(e) => setSeeds(+e.target.value)}
            />
          </label>
          <label className="font-mono text-[11px] uppercase tracking-[0.1em] text-soft">
            Read copies
            <input
              type="number"
              min={1}
              max={30}
              className="field mt-1 w-20"
              value={copies}
              onChange={(e) => setCopies(+e.target.value)}
            />
          </label>
          <label className="font-mono text-[11px] uppercase tracking-[0.1em] text-soft">
            Dropout
            <input
              type="number"
              min={0}
              max={0.9}
              step={0.01}
              className="field mt-1 w-24"
              value={dropout}
              onChange={(e) => setDropout(+e.target.value)}
            />
          </label>
          <label className="flex items-center gap-2 pb-3 font-mono text-[11px] uppercase tracking-[0.06em]">
            <input type="checkbox" className="accent-brand" checked={rsOn} onChange={(e) => setRsOn(e.target.checked)} /> Also
            test with 30% Reed-Solomon
          </label>
          <button className="btn-primary" disabled={busy || !chosen.length || !rates.length} onClick={run}>
            {busy ? <Spinner label={`Running ${nRuns} simulations`} /> : `Run ${nRuns} simulations`}
          </button>
        </div>
        <ErrorNote error={err} />
      </div>

      {!bench ? (
        <div className="mt-8">
          <Empty title="No benchmark for this file yet">Choose codecs and rates above, then run.</Empty>
        </div>
      ) : (
        <div className="mt-8 space-y-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-soft">
              Benchmark #{bench.id}: {bench.n_runs} runs. <SimBadge className="ml-1" />
            </p>
            <div className="flex gap-2">
              <a className="btn-ghost no-underline" href={url(`/benchmark/${bench.id}/csv`)}>
                Download CSV
              </a>
              <Link to="/recommend" className="btn-brand no-underline">
                Get a recommendation
              </Link>
            </div>
          </div>
          <div className="overflow-x-auto rounded-xl border border-line bg-white">
            <table className="w-full text-left text-sm">
              <thead className="bg-paper text-xs text-soft">
                <tr>
                  <th className="px-3 py-2">Variant</th>
                  <th>
                    <Term tip="Share of tested error rates (averaged over seeds) with byte-exact recovery.">Survival</Term>
                  </th>
                  <th>
                    <Term tip="Highest tested error rate where every seed, and every lower rate, recovered exactly.">
                      Tolerance
                    </Term>
                  </th>
                  <th>Density</th>
                  <th>GC</th>
                  <th>Max run</th>
                  <th>Constraints</th>
                  {hasLLM && <th>LLM readiness</th>}
                  <th>Retrieval</th>
                </tr>
              </thead>
              <tbody>
                {perVariant.map(({ v, first, survival, llm, rt }) => (
                  <tr key={v} className="border-t border-line">
                    <td className="px-3 py-2 font-bold">{v}</td>
                    <td className="tabular">{pct(survival, 0)}</td>
                    <td className="tabular">{first.error_tolerance == null ? "none" : pct(first.error_tolerance, 1)}</td>
                    <td className="tabular">{num(first.density_bits_per_nt, 3)}</td>
                    <td className="tabular">{pct(first.gc, 0)}</td>
                    <td className="tabular">{first.max_homopolymer}</td>
                    <td>
                      <Badge tone={statusTone(first.constraint_status)}>{first.constraint_status}</Badge>
                    </td>
                    {hasLLM && <td className="tabular">{llm == null ? "–" : llm.toFixed(0)}</td>}
                    <td className="tabular">{ms(rt)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="grid gap-6 lg:grid-cols-2">
            <MetricChart rows={bench.summary} metric="exact_match_mean" title="Byte-exact recovery" yLabel="% of seeds" />
            <MetricChart rows={bench.summary} metric="file_byte_accuracy_mean" title="File byte accuracy" yLabel="% bytes" />
            {hasLLM && (
              <MetricChart
                rows={bench.summary}
                metric="llm_readiness_mean"
                title="LLM readiness of recovered text"
                yLabel="score /100"
                percent={false}
              />
            )}
          </div>
        </div>
      )}
    </NeedFile>
  );
}
