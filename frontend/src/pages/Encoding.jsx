import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { get, post } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";
import { NeedFile } from "@/components/NeedFile";
import { EncodingSummary } from "@/components/EncodingSummary";
import { ErrorNote, PageHead, Spinner, StatusBadge, Term } from "@/components/ui";

export default function EncodingPage() {
  const ws = useWorkspace();
  const [codecs, setCodecs] = useState([]);
  const [codec, setCodec] = useState("church");
  const [rs, setRs] = useState(25);
  const [payload, setPayload] = useState("");
  const [primers, setPrimers] = useState(false);
  const [overhead, setOverhead] = useState(0.4);
  const [imageMode, setImageMode] = useState("pixels");
  const [compress, setCompress] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [enc, setEnc] = useState(null);

  useEffect(() => {
    get("/codecs")
      .then(setCodecs)
      .catch((e) => setErr(e.message));
  }, []);
  useEffect(() => {
    if (ws.encodingId)
      get(`/encoding/${ws.encodingId}`)
        .then(setEnc)
        .catch(() => {});
  }, [ws.encodingId]);
  const sel = codecs.find((c) => c.name === codec);

  const run = async () => {
    if (!ws.file) return;
    setBusy(true);
    setErr(null);
    try {
      const body = { file_id: ws.file.id, codec, compress, primers };
      if (sel?.supports_rs) body.rs_parity_pct = rs;
      if (payload) body.payload_bytes = payload;
      if (codec === "fountain") body.overhead = overhead;
      if (ws.file.kind === "image") body.image_mode = imageMode;
      const e = await post("/encoding/run", body);
      setEnc(e);
      ws.set({ encodingId: e.id, simulationId: null, retrievalId: null });
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <NeedFile>
      <PageHead
        title="Encode into DNA"
        lead={
          <>
            Turn <b>{ws.file?.filename}</b> into oligos. Codecs marked future work are listed for comparison and cannot run.
          </>
        }
      />
      <div className="grid gap-6 lg:grid-cols-[1.3fr_1fr]">
        <fieldset>
          <legend className="label">Codec</legend>
          <div className="grid gap-3 sm:grid-cols-2">
            {codecs.map((c) => {
              const off = c.status === "future_work";
              return (
                <button
                  key={c.name}
                  disabled={off}
                  onClick={() => setCodec(c.name)}
                  aria-pressed={codec === c.name}
                  className={`rounded-xl border-[1.5px] p-4 text-left transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${codec === c.name ? "border-ink bg-brand-tint" : "border-ink/25 bg-white hover:border-ink"}`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-display text-base">{c.label}</span>
                    <StatusBadge status={c.status} />
                  </div>
                  <p className="mt-1 text-sm text-soft">{c.description}</p>
                </button>
              );
            })}
          </div>
        </fieldset>
        <div className="panel h-fit space-y-5">
          {sel?.supports_rs && (
            <div>
              <label className="label" htmlFor="rs">
                <Term tip="Reed-Solomon parity oligos added per block. They let the decoder rebuild lost or rejected oligos (erasures). More parity = more DNA.">
                  Reed-Solomon parity
                </Term>
                : {rs}%
              </label>
              <input
                id="rs"
                type="range"
                min={0}
                max={100}
                step={5}
                value={rs}
                onChange={(e) => setRs(+e.target.value)}
                className="w-full accent-brand"
              />
            </div>
          )}
          {sel?.supports_rs && (
            <div>
              <label className="label" htmlFor="pb">
                Payload bytes per oligo (blank = codec default)
              </label>
              <input
                id="pb"
                type="number"
                min={8}
                max={128}
                className="field"
                value={payload}
                onChange={(e) => setPayload(e.target.value ? +e.target.value : "")}
              />
            </div>
          )}
          {codec === "fountain" && (
            <div>
              <label className="label" htmlFor="ov">
                <Term tip="Extra droplets beyond the number of source segments. Fountain codes need some surplus to decode after losses.">
                  Droplet overhead
                </Term>
                : {Math.round(overhead * 100)}%
              </label>
              <input
                id="ov"
                type="range"
                min={0.1}
                max={1.5}
                step={0.05}
                value={overhead}
                onChange={(e) => setOverhead(+e.target.value)}
                className="w-full accent-brand"
              />
            </div>
          )}
          {ws.file?.kind === "image" && (
            <div>
              <label className="label" htmlFor="im">
                Image storage mode
              </label>
              <select id="im" className="field" value={imageMode} onChange={(e) => setImageMode(e.target.value)}>
                <option value="pixels">Raw pixels (degrades gracefully)</option>
                <option value="pixels_gray">Raw grayscale pixels (3x smaller)</option>
                <option value="file">Original file bytes (compact, all-or-nothing)</option>
              </select>
            </div>
          )}
          {sel?.supports_rs && (
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={primers} onChange={(e) => setPrimers(e.target.checked)} className="accent-brand" />{" "}
              Add 20-nt primers to each end
            </label>
          )}
          <label className="flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              checked={compress}
              onChange={(e) => setCompress(e.target.checked)}
              className="mt-1 accent-brand"
            />
            <span>
              Compress before encoding
              <span className="block text-xs font-normal text-soft">
                Fewer oligos, but one bad bit can make the whole file unreadable.
              </span>
            </span>
          </label>
          <button className="btn-primary w-full" onClick={run} disabled={busy || !sel || sel.status === "future_work"}>
            {busy ? <Spinner label="Encoding" /> : `Encode with ${sel?.label ?? codec}`}
          </button>
          <ErrorNote error={err} />
        </div>
      </div>
      {enc && (
        <div className="mt-8 space-y-4">
          <EncodingSummary e={enc} />
          <div className="flex flex-wrap gap-3">
            <Link to="/sequences" className="btn-ghost no-underline">
              Inspect sequences
            </Link>
            <Link to="/twin" className="btn-primary no-underline">
              Age and misread it
            </Link>
          </div>
        </div>
      )}
    </NeedFile>
  );
}
