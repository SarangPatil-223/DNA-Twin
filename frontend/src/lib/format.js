export const pct = (v, d = 1) => (v == null || Number.isNaN(v) ? "–" : `${(v * 100).toFixed(d)}%`);
export const num = (v, d = 2) => (v == null || Number.isNaN(v) ? "–" : v.toFixed(d));
export const bytes = (n) =>
  n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1048576).toFixed(2)} MB`;
export const ms = (v) => (v == null ? "–" : v < 1000 ? `${v.toFixed(0)} ms` : `${(v / 1000).toFixed(2)} s`);
export const statusTone = (s) =>
  s === "VALID" || s === "implemented" ? "ok" : s === "WARNING" || s === "simplified" ? "warn" : "bad";
