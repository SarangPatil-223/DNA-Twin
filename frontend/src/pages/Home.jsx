import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { get, post, upload, url } from "@/lib/api";
import { QUESTION, YEAR } from "@/lib/codecCopy";
import { useWorkspace } from "@/lib/workspace";
import { Seq } from "@/components/Seq";
import { ErrorNote, SimBadge, Spinner, StatusBadge } from "@/components/ui";

const SAMPLE = "This is a sample AI model checkpoint metadata file used to demonstrate DNA storage encoding comparison.";

const DEMO = [
  {
    key: "church",
    title: "Church",
    sub: "1 bit per base + Reed-Solomon",
    head: "bg-amber-tint",
    accent: "text-amber",
    bar: "bg-amber",
    body: { codec: "church", rs_parity_pct: 25 },
  },
  {
    key: "goldman",
    title: "Goldman",
    sub: "rotating, no repeats, 4x overlap",
    head: "bg-brand-tint",
    accent: "text-brand",
    bar: "bg-brand",
    body: { codec: "goldman" },
  },
];

function Card({ title, sub, head, accent, bar, side }) {
  const s = side?.encoding.stats;
  const r = side?.retrieval;
  const acc = r ? 100 * (r.metrics.file_byte_accuracy ?? 0) : null;
  return (
    <div className="overflow-hidden rounded-xl border-[1.5px] border-ink bg-white">
      <div className={`flex items-center justify-between border-b-[1.5px] border-ink px-5 py-4 ${head}`}>
        <span className="font-display text-base">{title}</span>
        <span className="font-mono text-[10px] text-soft">{sub}</span>
      </div>
      <div className="p-5">
        <div className="mb-5 grid grid-cols-2 gap-x-4 gap-y-3.5">
          {[
            ["Density", s ? `${s.density_bits_per_nt.toFixed(3)} b/nt` : "—"],
            ["Length", s ? `${s.total_nt.toLocaleString()} nt` : "—"],
            ["GC content", s ? `${(s.gc * 100).toFixed(2)}%` : "—"],
            ["Max run", side ? String(side.encoding.constraints.max_homopolymer) : "—"],
          ].map(([l, v]) => (
            <div key={l}>
              <div className="mono-label mb-1">{l}</div>
              <div className="tabular font-mono text-[15px] font-semibold">{v}</div>
            </div>
          ))}
        </div>
        <div className="mono-label mb-1">Recovery accuracy</div>
        <div className={`tabular mb-2 font-display text-[38px] leading-none ${accent}`}>
          {acc == null ? "—" : `${acc.toFixed(2)}%`}
        </div>
        <div className="h-1.5 overflow-hidden rounded bg-line">
          <div className={`h-full ${bar}`} style={{ width: `${acc ?? 0}%` }} />
        </div>
        {r && (
          <span className={`chip mt-3.5 ${r.exact_match ? "bg-okTint text-ok" : "bg-badTint text-bad"}`}>
            {r.exact_match ? "Exact recovery" : "Not byte-exact"}
          </span>
        )}
        <div className="mt-4 max-h-16 overflow-hidden rounded-md border border-line bg-paper px-3 py-2">
          {side?.encoding.sample_oligos?.[0] ? (
            <Seq s={side.encoding.sample_oligos[0]} max={160} className="!text-[11px] !leading-[1.7]" />
          ) : (
            <span className="font-mono text-[11px] text-soft">—</span>
          )}
        </div>
        {r?.downloadable ? (
          <a href={url(`/retrieval/${r.id}/download`)} className="btn-ghost mt-4 w-full rounded-lg no-underline">
            Download recovered text
          </a>
        ) : (
          <button disabled className="btn-ghost mt-4 w-full rounded-lg">
            Download recovered text
          </button>
        )}
      </div>
    </div>
  );
}

export default function Home() {
  const ws = useWorkspace();
  const [tab, setTab] = useState("text");
  const [text, setText] = useState(SAMPLE);
  const [file, setFile] = useState(null);
  const [drag, setDrag] = useState(false);
  const [rate, setRate] = useState(1);
  const [seed, setSeed] = useState(42);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [demoFile, setDemoFile] = useState(null);
  const [sides, setSides] = useState({});
  const uploaded = useRef(null);
  const input = useRef(null);

  const [codecs, setCodecs] = useState([]);
  const [stats, setStats] = useState(null);
  const [bench, setBench] = useState(null);
  const [offline, setOffline] = useState(false);
  useEffect(() => {
    get("/codecs")
      .then(setCodecs)
      .catch(() => setOffline(true));
    get("/stats")
      .then(setStats)
      .catch(() => {});
    get("/benchmark/latest")
      .then(setBench)
      .catch(() => {});
  }, []);

  const run = async (r = rate, sd = seed) => {
    setBusy(true);
    setErr(null);
    try {
      const source = tab === "file" && file ? file : new File([text || " "], "quick-demo.txt", { type: "text/plain" });
      const key = tab === "file" && file ? `f:${file.name}:${file.size}:${file.lastModified}` : `t:${text}`;
      if (uploaded.current?.key !== key) uploaded.current = { key, row: await upload(source) };
      const row = uploaded.current.row;
      setDemoFile(row);
      const e = r / 100;
      const channel = { sub: e * 0.5, ins: e * 0.1, dele: e * 0.4, copies: 3, dropout: e > 0 ? 0.01 : 0, seed: sd };
      const out = {};
      for (const d of DEMO) {
        const res = await post("/pipeline/run", { file_id: row.id, ...d.body, ...channel });
        out[d.key] = res;
        setSides({ ...out });
      }
      get("/stats")
        .then(setStats)
        .catch(() => {});
    } catch (x) {
      setErr(x.message);
    } finally {
      setBusy(false);
    }
  };

  const survival = useMemo(() => {
    const m = new Map();
    const byVar = new Map();
    bench?.summary.forEach((r) => byVar.set(r.variant, [...(byVar.get(r.variant) ?? []), r]));
    byVar.forEach((rs, v) => {
      const sc = (100 * rs.reduce((a, r) => a + r.exact_match_mean, 0)) / rs.length;
      const c = rs[0].codec;
      if (!m.has(c) || sc > m.get(c).score) m.set(c, { score: sc, variant: v, density: rs[0].density_bits_per_nt });
    });
    return m;
  }, [bench]);

  const head = (st) => (st === "implemented" ? "bg-brand-tint" : st === "simplified" ? "bg-amber-tint" : "bg-badTint");

  return (
    <div className="-mt-8">
      <section className="border-b-[3px] border-ink pb-9 pt-14">
        <h1 className="mb-5 text-[clamp(34px,6vw,64px)] leading-[0.98]">
          Write it. Mutate it.
          <br />
          Get it <span className="text-brand">back.</span>
        </h1>
        <p className="max-w-[560px] text-base leading-relaxed text-soft">
          Type or drop a file, encode it into simulated DNA two different ways, then push the error rate up and watch which scheme
          actually survives. The full workbench is one click away.
        </p>
        {offline && (
          <p className="mt-4 font-mono text-[12px] text-bad">The API is not reachable. Start the backend on port 8000.</p>
        )}
      </section>

      <section className="border-b border-line py-8">
        <div className="mb-4 flex gap-2">
          {["text", "file"].map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              aria-pressed={tab === t}
              className={`rounded-full border-[1.5px] border-ink px-4 py-2 font-mono text-[12px] uppercase tracking-[0.06em] ${tab === t ? "bg-ink text-paper" : "bg-transparent"}`}
            >
              {t === "text" ? "Type text" : "Upload file"}
            </button>
          ))}
        </div>
        {tab === "text" ? (
          <label className="block">
            <span className="label">Input text</span>
            <textarea value={text} onChange={(e) => setText(e.target.value)} className="field min-h-[88px] resize-y p-3.5" />
          </label>
        ) : (
          <div>
            <span className="label">Input file</span>
            <div
              tabIndex={0}
              role="button"
              onClick={() => input.current?.click()}
              onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current?.click()}
              onDragOver={(e) => {
                e.preventDefault();
                setDrag(true);
              }}
              onDragLeave={() => setDrag(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDrag(false);
                if (e.dataTransfer.files[0]) setFile(e.dataTransfer.files[0]);
              }}
              className={`cursor-pointer rounded-lg border-[1.5px] border-dashed bg-white px-3.5 py-5 text-center font-mono text-[12px] ${drag ? "border-brand text-brand" : "border-ink text-soft"}`}
            >
              {file ? <span className="font-semibold text-ink">{file.name}</span> : "Click to choose a file, or drag one here"}
              <input
                ref={input}
                type="file"
                className="hidden"
                accept=".txt,.csv,.md,.json,.pdf,.docx"
                onChange={(e) => e.target.files?.[0] && setFile(e.target.files[0])}
              />
            </div>
          </div>
        )}
        <div className="mt-6 flex flex-wrap items-end gap-7">
          <div className="min-w-[220px] flex-1">
            <div className="mb-2 flex items-baseline justify-between">
              <label htmlFor="rate" className="label !mb-0">
                Simulated error rate
              </label>
              <b className="font-display text-xl font-normal text-brand">{rate.toFixed(1)}%</b>
            </div>
            <input
              id="rate"
              type="range"
              min={0}
              max={20}
              step={0.5}
              value={rate}
              className="w-full"
              onChange={(e) => setRate(+e.target.value)}
              onPointerUp={() => demoFile && run()}
              onKeyUp={() => demoFile && run()}
            />
          </div>
          <label className="w-[120px]">
            <span className="label">Seed</span>
            <input type="number" value={seed} className="field w-[90px] p-2.5" onChange={(e) => setSeed(+e.target.value || 42)} />
          </label>
          <button
            className="btn-primary px-7 py-3.5 text-[13px]"
            disabled={busy || (tab === "file" && !file)}
            onClick={() => run()}
          >
            Run
          </button>
        </div>
        <div className="mt-4 min-h-6">
          {busy && <Spinner label="Encoding, ageing and decoding" />}
          <ErrorNote error={err} />
        </div>
      </section>

      <section className="grid grid-cols-1 border-b border-line sm:grid-cols-3" aria-label="Current demo input">
        {[
          ["Bytes in", demoFile ? demoFile.size.toLocaleString() : "—"],
          ["Checksum", demoFile ? demoFile.sha256.slice(0, 8) : "—"],
          ["Error rate", `${rate.toFixed(1)}%`],
        ].map(([l, v], i) => (
          <div key={l} className={`py-7 text-center ${i < 2 ? "border-b border-line sm:border-b-0 sm:border-r" : ""}`}>
            <div className="tabular font-display text-[clamp(22px,4vw,34px)]">{v}</div>
            <div className="mono-label mt-1 !text-[11px]">{l}</div>
          </div>
        ))}
      </section>

      <section className="grid gap-5 py-8 md:grid-cols-2">
        {DEMO.map((d) => (
          <Card key={d.key} title={d.title} sub={d.sub} head={d.head} accent={d.accent} bar={d.bar} side={sides[d.key]} />
        ))}
      </section>

      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-line pb-8">
        <p className="max-w-[640px] text-[13px] leading-[1.7] text-soft">
          <b className="text-ink">Why they diverge:</b> Church stores one bit per base and relies on Reed-Solomon parity to
          rebuild lost oligos, so it recovers exactly until too many oligos fail at once. Goldman writes every stretch of data
          four times across overlapping fragments and never repeats a base, which costs about four times the DNA but lets damage
          stay local instead of wiping out whole blocks. Each read here is one of 3 noisy copies; errors are split 50%
          substitutions, 10% insertions, 40% deletions.
        </p>
        <div className="flex flex-col items-end gap-2">
          {Object.keys(sides).length > 0 && <SimBadge />}
          {demoFile && (
            <Link to="/encoding" onClick={() => ws.set({ file: demoFile })} className="btn-ghost no-underline">
              Open in workbench
            </Link>
          )}
        </div>
      </div>

      <section className="py-10">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
          <h2 className="text-[clamp(24px,3.5vw,36px)]">Every codec</h2>
          <p className="font-mono text-[11px] text-soft">
            {bench?.file
              ? `Survival from the latest benchmark on ${bench.file.filename} (${bench.n_runs} runs)`
              : "Survival appears after your first benchmark"}
          </p>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {codecs.map((c) => {
            const sv = survival.get(c.name);
            return (
              <article key={c.name} className="flex flex-col overflow-hidden rounded-xl border-[1.5px] border-ink bg-white">
                <div className={`flex items-center justify-between border-b-[1.5px] border-ink px-4 py-3 ${head(c.status)}`}>
                  <span className="font-display text-sm">{c.label}</span>
                  <span className="font-mono text-[10px] text-soft">{YEAR[c.name] || ""}</span>
                </div>
                <div className="flex flex-1 flex-col justify-between gap-4 p-4">
                  <p className="text-sm leading-snug">{QUESTION[c.name] ?? c.description}</p>
                  <div className="flex items-end justify-between gap-3">
                    <div className="space-y-1">
                      <StatusBadge status={c.status} />
                      <div className="font-mono text-[11px] text-soft">
                        {sv ? `${sv.density.toFixed(2)} bits/nt measured` : `${c.nominal_bits_per_nt.toFixed(2)} bits/nt nominal`}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="tabular font-display text-[30px] leading-none text-brand">
                        {sv ? sv.score.toFixed(0) : "—"}
                      </div>
                      <div className="mono-label mt-1">Survival</div>
                    </div>
                  </div>
                </div>
              </article>
            );
          })}
        </div>
      </section>

      <section className="grid grid-cols-2 border-y-[1.5px] border-ink md:grid-cols-4" aria-label="Activity on this installation">
        {[
          ["Files tested", stats?.files],
          ["Retrieval runs", stats?.retrievals],
          ["Byte-exact", stats?.exact_retrievals],
          ["Benchmark runs", stats?.benchmark_runs],
        ].map(([l, v], i) => (
          <div key={l} className={`py-6 text-center ${i < 3 ? "md:border-r md:border-line" : ""}`}>
            <div className="tabular font-display text-3xl">{v ?? "—"}</div>
            <div className="mono-label mt-1 !text-[11px]">{l}</div>
          </div>
        ))}
      </section>

      <section className="flex flex-wrap items-center justify-between gap-5 py-10">
        <p className="max-w-xl text-soft">
          The workbench takes one file through every step: encode, inspect sequences, age and misread, recover, compare every
          codec, and ask an LLM about whatever came back.
        </p>
        <div className="flex gap-3">
          <Link to="/upload" className="btn-primary no-underline">
            Upload a file
          </Link>
          <Link to="/compare" className="btn-ghost no-underline">
            Compare codecs
          </Link>
        </div>
      </section>
    </div>
  );
}
