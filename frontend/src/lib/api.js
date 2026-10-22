// Minimal API client. All calls go to /api/* (forwarded to FastAPI by vite.config.js in development and nginx.conf in Docker).
// Response shapes are documented in docs/api.md and at http://localhost:8000/docs.
export const API = import.meta.env.VITE_API_BASE || "/api";

export class ApiError extends Error {
  status;
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

async function handle(r) {
  if (!r.ok) {
    let msg = `${r.status} ${r.statusText}`;
    try {
      const j = await r.json();
      msg = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail ?? j);
    } catch {}
    throw new ApiError(r.status, msg);
  }
  return r.json();
}

export const get = (path) => fetch(`${API}${path}`, { cache: "no-store" }).then(handle);
export const post = (path, body) =>
  fetch(`${API}${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then(
    handle,
  );

export async function upload(file) {
  const fd = new FormData();
  fd.append("file", file);
  return fetch(`${API}/files/upload`, { method: "POST", body: fd }).then(handle);
}

export const url = (path) => `${API}${path}`;
