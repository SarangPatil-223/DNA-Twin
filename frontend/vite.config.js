import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development the browser calls /api/* on the Vite server, which forwards to FastAPI.
// In Docker, nginx does the same forwarding (see nginx.conf).
const backend = process.env.BACKEND_URL || "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": "/src" } },
  server: { port: 3000, proxy: { "/api": { target: backend, changeOrigin: true } } },
  preview: { port: 3000, proxy: { "/api": { target: backend, changeOrigin: true } } },
});
