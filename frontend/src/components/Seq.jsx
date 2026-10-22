// Colours each base so patterns (homopolymers, GC runs) are visible at a glance.
const C = { A: "text-baseA", C: "text-baseC", G: "text-baseG", T: "text-baseT" };

export function Seq({ s, max = 400, className = "" }) {
  const shown = s.slice(0, max);
  return (
    <code className={`block break-all font-mono text-[12px] leading-5 ${className}`}>
      {shown.split("").map((b, i) => (
        <span key={i} className={C[b] ?? "text-soft"}>
          {b}
        </span>
      ))}
      {s.length > max && <span className="text-soft">… (+{s.length - max} nt)</span>}
    </code>
  );
}

// Base-level diff: original on top, read below, with each edit marked.
export function SeqDiff({ original, read, ops }) {
  const origMark = new Map();
  const readMark = new Map();
  for (const [tag, s1, e1, s2, e2] of ops) {
    for (let i = s1; i < e1; i++) origMark.set(i, tag);
    for (let j = s2; j < e2; j++) readMark.set(j, tag);
    if (tag === "insert") origMark.set(s1, "insert-point");
  }
  const style = (t) =>
    t === "replace"
      ? "bg-baseG/30 rounded-sm"
      : t === "delete"
        ? "bg-baseT/25 line-through rounded-sm"
        : t === "insert"
          ? "bg-baseA/30 rounded-sm"
          : t === "insert-point"
            ? "border-l-2 border-baseA"
            : "";
  return (
    <div className="space-y-1 overflow-x-auto font-mono text-[12px] leading-5">
      <div className="whitespace-nowrap">
        <span className="mr-2 inline-block w-16 mono-label">Stored</span>
        {original.split("").map((b, i) => (
          <span key={i} className={style(origMark.get(i))}>
            {b}
          </span>
        ))}
      </div>
      <div className="whitespace-nowrap">
        <span className="mr-2 inline-block w-16 mono-label">Read</span>
        {read.split("").map((b, i) => (
          <span key={i} className={style(readMark.get(i))}>
            {b}
          </span>
        ))}
      </div>
    </div>
  );
}

export function DiffLegend() {
  return (
    <p className="flex flex-wrap gap-3 text-xs text-soft">
      <span>
        <span className="rounded-sm bg-baseG/30 px-1">C</span> substitution
      </span>
      <span>
        <span className="rounded-sm bg-baseT/25 px-1 line-through">A</span> deletion
      </span>
      <span>
        <span className="rounded-sm bg-baseA/30 px-1">G</span> insertion
      </span>
    </p>
  );
}
