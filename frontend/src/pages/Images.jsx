import { useEffect, useState } from "react";
import { get, post, upload } from "@/lib/api";
import { bytes, num, pct } from "@/lib/format";
import { useWorkspace } from "@/lib/workspace";
import { ImageStrip } from "@/components/RetrievalCard";
import { Badge, ErrorNote, PageHead, SimBadge, Spinner, Term } from "@/components/ui";

const MODES = [
  [
    "file",
    "Original file bytes",
    "PNG/JPEG as-is. Smallest, but compressed data usually becomes unreadable after a single uncorrected error.",
  ],
  ["pixels", "Raw colour pixels", "Downscaled RGB pixels. More DNA, but damage stays local, and lost regions can be filled in."],
  ["pixels_gray", "Raw grayscale pixels", "One byte per pixel: a third of the DNA of colour, same graceful damage."],
];

export default function ImagesPage() {
  const ws = useWorkspace();
  const [codecs, setCodecs] = useState([]);
  const [codec, setCodec] = useState("yinyang");
  const [rate, setRate] = useState(0.01);
  const [copies, setCopies] = useState(3);
  const [rs, setRs] = useState(0);
  const [outs, setOuts] = useState([]);
  const [busy, setBusy] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    get("/codecs")
      .then((c) => setCodecs(c.filter((x) => x.status !== "future_work")))
      .catch(() => {});
  }, []);
  const isImage = ws.file?.kind === "image";

  const run = async () => {
    if (!ws.file) return;
    setErr(null);
    setOuts([]);
    const sup = codecs.find((c) => c.name === codec)?.supports_rs;
    const res = [];
    try {
      for (const [mode, label] of MODES) {
        setBusy(`Storing as ${label.toLowerCase()}`);
        const r = await post("/pipeline/run", {
          file_id: ws.file.id,
          codec,
          image_mode: mode,
          sub: rate * 0.5,
          ins: rate * 0.1,
          dele: rate * 0.4,
          copies,
          seed: 11,
          dropout: rate > 0 ? 0.01 : 0,
          ...(sup ? { rs_parity_pct: rs } : {}),
          ...(codec === "fountain" ? { overhead: 0.4 } : {}),
        });
        res.push({ mode, ...r });
        setOuts([...res]);
      }
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div>
      <PageHead
        title="Image lab"
        lead="The same picture stored three ways, pushed through the same noisy channel. Compare how much of it you can still see, measured with PSNR and SSIM."
      />
      {!isImage ? (
        <div className="panel">
          <p className="font-bold">Pick or upload an image (PNG or JPG).</p>
          <input
            type="file"
            accept=".png,.jpg,.jpeg"
            className="mt-3 text-sm"
            aria-label="Upload an image"
            onChange={async (e) => {
              const f = e.target.files?.[0];
              if (!f) return;
              try {
                ws.set({ file: await upload(f) });
              } catch (x) {
                setErr(x.message);
              }
            }}
          />
          <ErrorNote error={err} />
        </div>
      ) : (
        <>
          <div className="panel flex flex-wrap items-end gap-5">
            <p className="w-full text-sm text-soft">
              Image: <b className="text-ink">{ws.file.filename}</b> ({bytes(ws.file.size)})
            </p>
            <label className="font-mono text-[11px] uppercase tracking-[0.1em] text-soft">
              Codec
              <select className="field mt-1 w-44" value={codec} onChange={(e) => setCodec(e.target.value)}>
                {codecs.map((c) => (
                  <option key={c.name} value={c.name}>
                    {c.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="font-mono text-[11px] uppercase tracking-[0.1em] text-soft">
              Error rate {pct(rate, 1)}
              <input
                type="range"
                min={0}
                max={0.05}
                step={0.0025}
                value={rate}
                onChange={(e) => setRate(+e.target.value)}
                className="mt-2 block w-48 accent-brand"
              />
            </label>
            <label className="font-mono text-[11px] uppercase tracking-[0.1em] text-soft">
              Read copies
              <input
                type="number"
                min={1}
                max={20}
                className="field mt-1 w-20"
                value={copies}
                onChange={(e) => setCopies(+e.target.value)}
              />
            </label>
            {codecs.find((c) => c.name === codec)?.supports_rs && (
              <label className="font-mono text-[11px] uppercase tracking-[0.1em] text-soft">
                RS parity %
                <input
                  type="number"
                  min={0}
                  max={100}
                  step={5}
                  className="field mt-1 w-20"
                  value={rs}
                  onChange={(e) => setRs(+e.target.value)}
                />
              </label>
            )}
            <button className="btn-primary" onClick={run} disabled={!!busy}>
              Store all three ways
            </button>
            {busy && <Spinner label={busy} />}
            <ErrorNote error={err} />
          </div>
          <div className="mt-8 space-y-6">
            {outs.map((o) => {
              const [, label, what] = MODES.find((m) => m[0] === o.mode);
              const im = o.retrieval.image_metrics;
              return (
                <section key={o.mode} className="panel space-y-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <h3 className="text-xl">{label}</h3>
                      <p className="text-sm text-soft">{what}</p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone="neutral">{o.encoding.stats.total_nt.toLocaleString()} nt</Badge>
                      {o.retrieval.exact_match ? (
                        <Badge tone="ok">byte-exact</Badge>
                      ) : im.raw.decodable ? (
                        <Badge tone="warn">damaged but viewable</Badge>
                      ) : (
                        <Badge tone="bad">unreadable</Badge>
                      )}
                      <SimBadge />
                    </div>
                  </div>
                  <ImageStrip r={o.retrieval} />
                </section>
              );
            })}
          </div>
          {outs.length === 3 && (
            <section className="mt-8 panel">
              <h3 className="font-display text-base">Side by side</h3>
              <div className="mt-3 overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="text-xs text-soft">
                    <tr>
                      <th className="py-1">Storage</th>
                      <th>DNA used</th>
                      <th>Result</th>
                      <th>
                        <Term tip="Structural similarity: 1.0 is identical, below ~0.5 the picture is hard to recognise.">
                          SSIM
                        </Term>
                      </th>
                      <th>SSIM after concealment</th>
                      <th>
                        <Term tip="Peak signal-to-noise ratio in dB. Higher is better; ∞ means identical.">PSNR</Term>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {outs.map((o) => {
                      const im = o.retrieval.image_metrics;
                      return (
                        <tr key={o.mode} className="border-t border-line">
                          <td className="py-1.5 font-bold">{MODES.find((m) => m[0] === o.mode)[1]}</td>
                          <td className="tabular">{o.encoding.stats.total_nt.toLocaleString()} nt</td>
                          <td>{o.retrieval.exact_match ? "exact" : im.raw.decodable ? "damaged" : "unreadable"}</td>
                          <td className="tabular">{num(im.raw.ssim, 3)}</td>
                          <td className="tabular">{num(im.concealed.ssim, 3)}</td>
                          <td className="tabular">{im.raw.psnr_infinite ? "∞" : num(im.raw.psnr_db, 1)}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <p className="mt-3 text-sm text-soft">
                Concealment fills zero-filled pixels by averaging their known neighbours, which works because the decoder knows
                exactly which oligos were lost.
              </p>
            </section>
          )}
        </>
      )}
    </div>
  );
}
