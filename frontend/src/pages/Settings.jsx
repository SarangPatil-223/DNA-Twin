import { useEffect, useState } from "react";
import { get } from "@/lib/api";
import { Badge, ErrorNote, PageHead } from "@/components/ui";

export default function SettingsPage() {
  const [s, setS] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    get("/settings")
      .then(setS)
      .catch((e) => setErr(e.message));
  }, []);
  const row = (k, v) => (
    <div className="flex flex-wrap justify-between gap-2 border-t border-line py-2.5 first:border-0">
      <span className="font-semibold">{k}</span>
      <span className="text-soft">{v}</span>
    </div>
  );
  return (
    <div>
      <PageHead
        title="Settings"
        lead="Providers are chosen from environment variables on the backend. Keys never pass through the browser."
      />
      <ErrorNote error={err} />
      {s && (
        <div className="grid gap-6 md:grid-cols-2">
          <section className="panel">
            <h2 className="mb-2 font-display text-base">Language model</h2>
            {row(
              "Answering with",
              <>
                {s.llm_provider} {s.llm_is_model ? <Badge tone="ok">LLM</Badge> : <Badge tone="warn">no LLM</Badge>}
              </>,
            )}
            {row("Gemini key set", s.gemini_key_set ? "yes" : "no")}
            {row("Gemini model", s.gemini_model)}
            {row("Anthropic key set", s.anthropic_key_set ? "yes" : "no")}
            {row("Anthropic model", s.anthropic_model)}
            {row("Ollama URL", s.ollama_url)}
            {row("Embeddings", `${s.embedding} (${s.embedding_dim} dims)`)}
          </section>
          <section className="panel">
            <h2 className="mb-2 font-display text-base">Storage</h2>
            {row("Database", s.database)}
            {row("Vector store", s.vector_store)}
            {row("Upload limit", `${s.max_upload_mb} MB`)}
            {row("OCR for images", s.ocr_available ? "tesseract installed" : "not installed")}
          </section>
          <section className="panel md:col-span-2">
            <h2 className="mb-2 font-display text-base">How to change them</h2>
            <pre className="overflow-x-auto rounded-lg bg-ink p-4 font-mono text-xs text-paper">{`# backend/.env or docker compose environment
LLM_PROVIDER=auto            # auto | gemini | anthropic | ollama | extractive
GEMINI_API_KEY=...           # enables Gemini answers
GEMINI_MODEL=${s.gemini_model}
ANTHROPIC_API_KEY=...        # enables Claude answers
ANTHROPIC_MODEL=${s.anthropic_model}
OLLAMA_URL=http://localhost:11434
EMBEDDING_PROVIDER=auto      # auto | hashing | sentence-transformers | ollama
QDRANT_URL=http://qdrant:6333
DATABASE_URL=postgresql+psycopg://dnatwin:...@postgres:5432/dnatwin`}</pre>
          </section>
        </div>
      )}
    </div>
  );
}
