import { Link } from "react-router-dom";
import { useState } from "react";
import { statusTone } from "@/lib/format";

export function SimBadge({ className = "" }) {
  return (
    <span
      className={`chip bg-brand-tint text-brand-deep ${className}`}
      title="Produced by a software simulation. No DNA was synthesized or sequenced."
    >
      Simulation result
    </span>
  );
}

const TONES = {
  ok: "bg-okTint text-ok",
  warn: "bg-warnTint text-warn",
  bad: "bg-badTint text-bad",
  neutral: "bg-paper text-soft border border-line",
};

export function Badge({ tone = "neutral", children, title }) {
  return (
    <span title={title} className={`chip ${TONES[tone] ?? TONES.neutral}`}>
      {children}
    </span>
  );
}

export function StatusBadge({ status }) {
  const text = status === "future_work" ? "Future work" : status.charAt(0).toUpperCase() + status.slice(1).toLowerCase();
  return <Badge tone={statusTone(status)}>{text}</Badge>;
}

export function Term({ children, tip }) {
  const [open, setOpen] = useState(false);
  return (
    <span className="relative inline-block">
      <button
        type="button"
        className="cursor-help border-b border-dotted border-soft text-left"
        aria-label={tip}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
      >
        {children}
      </button>
      {open && (
        <span
          role="tooltip"
          className="absolute left-0 top-full z-30 mt-1 w-64 rounded-lg bg-ink p-3 font-body text-xs font-medium normal-case leading-relaxed tracking-normal text-paper"
        >
          {tip}
        </span>
      )}
    </span>
  );
}

export function PageHead({ title, lead, children }) {
  return (
    <header className="mb-8 flex flex-col gap-5 border-b-[3px] border-ink pb-8 pt-6 md:flex-row md:items-end md:justify-between">
      <div className="max-w-2xl">
        <h1 className="text-[clamp(32px,5vw,56px)] leading-[0.98]">{title}</h1>
        {lead && <p className="mt-4 max-w-[560px] text-base leading-relaxed text-soft">{lead}</p>}
      </div>
      {children}
    </header>
  );
}

export function ErrorNote({ error }) {
  if (!error) return null;
  return (
    <p role="alert" className="rounded-lg border-[1.5px] border-bad bg-badTint px-4 py-3 font-mono text-[12px] text-bad">
      {error}
    </p>
  );
}

export function Empty({ title, children, href, cta }) {
  return (
    <div className="rounded-xl border-[1.5px] border-dashed border-ink bg-white px-6 py-10 text-center">
      <p className="font-display text-xl uppercase">{title}</p>
      {children && <p className="mx-auto mt-2 max-w-md text-sm text-soft">{children}</p>}
      {href && cta && (
        <Link to={href} className="btn-primary mt-5 no-underline">
          {cta}
        </Link>
      )}
    </div>
  );
}

export function Stat({ label, value, hint }) {
  return (
    <div>
      <p className="mono-label">{label}</p>
      <p className="tabular mt-1 font-mono text-[18px] font-semibold">{value}</p>
      {hint && <p className="mt-0.5 font-mono text-[11px] text-soft">{hint}</p>}
    </div>
  );
}

export function Spinner({ label = "Working" }) {
  return (
    <span className="inline-flex items-center gap-2 font-mono text-[12px] uppercase tracking-[0.06em] text-soft" role="status">
      <span className="flex gap-0.5" aria-hidden>
        {["bg-baseA", "bg-baseC", "bg-baseG", "bg-baseT"].map((c, i) => (
          <span key={c} className={`h-2 w-2 animate-bounce rounded-full ${c}`} style={{ animationDelay: `${i * 90}ms` }} />
        ))}
      </span>
      {label}
    </span>
  );
}

export function ScorePill({ score, label = "Survival score" }) {
  return (
    <div className="inline-flex flex-col items-end">
      <span className="tabular font-display text-[38px] leading-none text-brand">{score == null ? "–" : score.toFixed(0)}</span>
      <span className="mono-label mt-1">{label}</span>
    </div>
  );
}
