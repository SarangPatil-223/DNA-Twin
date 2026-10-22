import { createContext, useCallback, useContext, useEffect, useState } from "react";
// The working set a researcher moves through: one file, and the latest run at each stage.
const Empty = { file: null, encodingId: null, simulationId: null, retrievalId: null };
const C = createContext({ ...Empty, set: () => {}, ready: false });
const KEY = "dna-twin-workspace";

export function WorkspaceProvider({ children }) {
  const [ws, setWs] = useState(Empty);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(KEY);
      if (raw) setWs({ ...Empty, ...JSON.parse(raw) });
    } catch {}
    setReady(true);
  }, []);
  const set = useCallback((patch) => {
    setWs((prev) => {
      const next = { ...prev, ...patch };
      if (patch.file && patch.file.id !== prev.file?.id)
        Object.assign(next, { encodingId: null, simulationId: null, retrievalId: null }, patch);
      try {
        window.localStorage.setItem(KEY, JSON.stringify(next));
      } catch {}
      return next;
    });
  }, []);
  return <C.Provider value={{ ...ws, set, ready }}>{children}</C.Provider>;
}

export const useWorkspace = () => useContext(C);
