import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { get, upload } from "@/lib/api";
import { bytes } from "@/lib/format";
import { useWorkspace } from "@/lib/workspace";
import { Empty, ErrorNote, PageHead, Spinner } from "@/components/ui";

export default function UploadPage() {
  const ws = useWorkspace();
  const navigate = useNavigate();
  const [files, setFiles] = useState([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [drag, setDrag] = useState(false);
  const input = useRef(null);

  const refresh = () =>
    get("/files")
      .then(setFiles)
      .catch((e) => setErr(e.message));
  useEffect(() => {
    refresh();
  }, []);

  const send = async (f) => {
    if (!f) return;
    setBusy(true);
    setErr(null);
    try {
      const row = await upload(f);
      ws.set({ file: row });
      await refresh();
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <PageHead
        title="Upload a file"
        lead="Text, CSV, Markdown, JSON, PDF, DOCX, PNG or JPG, up to 2 MB. Files are stored under a hash name and never executed."
      />
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          send(e.dataTransfer.files[0]);
        }}
        className={`flex flex-col items-center justify-center rounded-xl border-[1.5px] border-dashed px-6 py-14 text-center transition-colors ${drag ? "border-brand bg-brand-tint" : "border-ink/40 bg-white"}`}
      >
        <p className="font-display text-xl">Drop a file here</p>
        <p className="mt-1 text-sm text-soft">or</p>
        <button className="btn-primary mt-3" onClick={() => input.current?.click()} disabled={busy}>
          Choose a file
        </button>
        <input
          ref={input}
          type="file"
          className="sr-only"
          aria-label="Choose a file"
          accept=".txt,.csv,.md,.json,.pdf,.docx,.png,.jpg,.jpeg"
          onChange={(e) => send(e.target.files?.[0])}
        />
        {busy && (
          <div className="mt-4">
            <Spinner label="Uploading" />
          </div>
        )}
      </div>
      <div className="mt-4">
        <ErrorNote error={err} />
      </div>

      <h2 className="mb-3 mt-10 text-2xl">Your files</h2>
      {files.length === 0 ? (
        <Empty title="No files yet">Upload one above to start.</Empty>
      ) : (
        <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line bg-white">
          {files.map((f) => {
            const current = ws.file?.id === f.id;
            return (
              <li key={f.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                <div className="min-w-0">
                  <p className="truncate font-bold">{f.filename}</p>
                  <p className="text-xs text-soft">
                    {f.kind === "image" ? "Image" : "Document"}, {bytes(f.size)}, SHA-256{" "}
                    <span className="font-mono">{f.sha256.slice(0, 12)}…</span>
                  </p>
                </div>
                <div className="flex gap-2">
                  {current ? (
                    <span className="chip border-ink bg-ink text-paper">Current file</span>
                  ) : (
                    <button className="btn-ghost py-1.5" onClick={() => ws.set({ file: f })}>
                      Use this file
                    </button>
                  )}
                  <button
                    className="btn-brand py-1.5"
                    onClick={() => {
                      ws.set({ file: f });
                      navigate(f.kind === "image" ? "/images" : "/encoding");
                    }}
                  >
                    {f.kind === "image" ? "Open in image lab" : "Encode"}
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
