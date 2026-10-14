"use client";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, client } from "./api";
import type { AccessConfig, DocumentInfo } from "./types";
import { DEFAULT_ACCESS } from "./types";

export interface Activity {
  id: number;
  screen: string;
  summary: string;
  at: number;
}

interface AppState {
  ready: boolean;
  sessionId: string | null;
  backendError: string | null;
  documents: DocumentInfo[];
  selected: string[];
  access: AccessConfig;
  accessOpen: boolean;
  activity: Activity[];
  theme: "dark" | "light";
  setAccess: (a: AccessConfig) => void;
  openAccess: (open: boolean) => void;
  refreshDocuments: () => Promise<void>;
  upload: (files: FileList | File[]) => Promise<void>;
  removeDocument: (id: string) => Promise<void>;
  toggleSelected: (id: string) => void;
  setSelected: (ids: string[]) => void;
  endSession: () => Promise<void>;
  log: (screen: string, summary: string) => void;
  toggleTheme: () => void;
}

const Ctx = createContext<AppState | null>(null);
export const useApp = () => {
  const v = useContext(Ctx);
  if (!v) throw new Error("useApp must be used inside AppProvider");
  return v;
};

// sessionStorage: survives a reload but dies with the tab, matching "nothing kept after the session".
const ss = {
  get: (k: string) => { try { return window.sessionStorage.getItem(k); } catch { return null; } },
  set: (k: string, v: string | null) => { try { v === null ? window.sessionStorage.removeItem(k) : window.sessionStorage.setItem(k, v); } catch { /* storage blocked */ } },
};

export function AppProvider({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [backendError, setBackendError] = useState<string | null>(null);
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [access, setAccessState] = useState<AccessConfig>(DEFAULT_ACCESS);
  const [accessOpen, openAccess] = useState(false);
  const [activity, setActivity] = useState<Activity[]>([]);
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  const counter = useRef(0);

  const newSession = useCallback(async () => {
    const s = await client.createSession();
    client.sessionId = s.session_id;
    ss.set("session", s.session_id);
    setSessionId(s.session_id);
    setDocuments([]);
    setSelected([]);
    return s.session_id;
  }, []);

  useEffect(() => {
    client.onSessionExpired = newSession;
    const storedAccess = ss.get("access");
    if (storedAccess) {
      const a = { ...DEFAULT_ACCESS, ...JSON.parse(storedAccess) } as AccessConfig;
      setAccessState(a);
      client.access = a;
    }
    const storedActivity = ss.get("activity");
    if (storedActivity) setActivity(JSON.parse(storedActivity));
    try {
      const t = window.localStorage.getItem("theme");
      if (t === "light" || t === "dark") setTheme(t);
    } catch { /* ignore */ }
    (async () => {
      try {
        const existing = ss.get("session");
        if (existing) {
          client.sessionId = existing;
          setSessionId(existing);
          setDocuments(await client.listDocuments()); // a 401 transparently creates a fresh session
        } else {
          await newSession();
        }
        setBackendError(null);
      } catch (e) {
        setBackendError(e instanceof ApiError ? e.message : "Cannot reach the backend. Is it running?");
      } finally {
        setReady(true);
      }
    })();
  }, [newSession]);

  useEffect(() => { document.documentElement.dataset.theme = theme; }, [theme]);

  const refreshDocuments = useCallback(async () => {
    const docs = await client.listDocuments();
    setDocuments(docs);
    setSelected((sel) => sel.filter((id) => docs.some((d) => d.id === id)));
    setSessionId(client.sessionId);
  }, []);

  const upload = useCallback(async (files: FileList | File[]) => {
    for (const f of Array.from(files)) {
      const doc = await client.uploadDocument(f);
      setDocuments((prev) => (prev.some((d) => d.id === doc.id) ? prev : [...prev, doc]));
      setSelected((prev) => (prev.includes(doc.id) ? prev : [...prev, doc.id]));
    }
    setSessionId(client.sessionId);
  }, []);

  const removeDocument = useCallback(async (id: string) => {
    await client.deleteDocument(id);
    setDocuments((prev) => prev.filter((d) => d.id !== id));
    setSelected((prev) => prev.filter((d) => d !== id));
  }, []);

  const setAccess = useCallback((a: AccessConfig) => {
    client.access = a;
    setAccessState(a);
    ss.set("access", JSON.stringify(a));
  }, []);

  const endSession = useCallback(async () => {
    const id = client.sessionId;
    if (id) await client.endSession(id).catch(() => undefined);
    ss.set("activity", null);
    setActivity([]);
    await newSession();
  }, [newSession]);

  const log = useCallback((screen: string, summary: string) => {
    setActivity((prev) => {
      const next = [{ id: ++counter.current + Date.now(), screen, summary, at: Date.now() }, ...prev].slice(0, 20);
      ss.set("activity", JSON.stringify(next));
      return next;
    });
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme((t) => {
      const next = t === "dark" ? "light" : "dark";
      try { window.localStorage.setItem("theme", next); } catch { /* ignore */ }
      return next;
    });
  }, []);

  const toggleSelected = useCallback(
    (id: string) => setSelected((prev) => (prev.includes(id) ? prev.filter((d) => d !== id) : [...prev, id])), []);

  const value = useMemo<AppState>(() => ({
    ready, sessionId, backendError, documents, selected, access, accessOpen, activity, theme, setAccess, openAccess,
    refreshDocuments, upload, removeDocument, toggleSelected, setSelected, endSession, log, toggleTheme,
  }), [ready, sessionId, backendError, documents, selected, access, accessOpen, activity, theme, setAccess,
    refreshDocuments, upload, removeDocument, toggleSelected, endSession, log, toggleTheme]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
