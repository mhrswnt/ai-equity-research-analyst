"use client";
import { useEffect, useState } from "react";
import { client } from "@/lib/api";
import { useApp } from "@/lib/store";
import type { AccessConfig, ModelsCatalog } from "@/lib/types";

export function AccessModal() {
  const { access, setAccess, accessOpen, openAccess } = useApp();
  const [draft, setDraft] = useState<AccessConfig>(access);
  const [catalog, setCatalog] = useState<ModelsCatalog | null>(null);
  const [status, setStatus] = useState<{ ok: boolean; text: string } | null>(null);
  const [testing, setTesting] = useState(false);

  useEffect(() => { if (accessOpen) { setDraft(access); setStatus(null); } }, [accessOpen, access]);
  useEffect(() => { if (accessOpen && !catalog) client.models().then(setCatalog).catch(() => undefined); }, [accessOpen, catalog]);
  if (!accessOpen) return null;

  const suggestions = catalog?.byok_providers[draft.provider]?.suggested ?? [];
  const defaultModel = catalog?.byok_providers[draft.provider]?.default ?? "";
  const set = (patch: Partial<AccessConfig>) => { setDraft({ ...draft, ...patch }); setStatus(null); };

  async function test() {
    setTesting(true);
    const previous = client.access;
    client.access = draft; // validate with the draft key without saving it
    try {
      await client.validateKey();
      setStatus({ ok: true, text: "Key works." });
    } catch (e) {
      setStatus({ ok: false, text: (e as Error).message });
    } finally {
      client.access = previous;
      setTesting(false);
    }
  }

  return (
    <div className="overlay" onClick={() => openAccess(false)}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2>Model access</h2>
        <p className="muted small" style={{ marginTop: 0 }}>
          Free models run on the server&apos;s keys for basic tasks. Bring your own key for strategy, comparison, research and custom analysis.
        </p>
        <div className="seg" style={{ margin: "12px 0 18px" }}>
          <button className={draft.mode === "free" ? "on" : ""} onClick={() => set({ mode: "free" })}>Free models</button>
          <button className={draft.mode === "byok" ? "on" : ""} onClick={() => set({ mode: "byok" })}>My own key</button>
        </div>

        {draft.mode === "free" ? (
          <div className="field">
            <label>Free model</label>
            <select className="input" value={draft.freeModel} onChange={(e) => set({ freeModel: e.target.value })}>
              <option value="">Server default</option>
              {(catalog?.free_models ?? []).map((m) => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>
        ) : (
          <>
            <div className="field">
              <label>Provider</label>
              <select className="input" value={draft.provider} onChange={(e) => set({ provider: e.target.value, model: "" })}>
                {Object.keys(catalog?.byok_providers ?? { anthropic: 1, openai: 1, gemini: 1, groq: 1, openrouter: 1 }).map((p) => <option key={p}>{p}</option>)}
              </select>
            </div>
            <div className="field">
              <label>Model {defaultModel ? `(default: ${defaultModel})` : "(required)"}</label>
              <input className="input" list="model-suggestions" value={draft.model} placeholder={defaultModel || "model id"}
                     onChange={(e) => set({ model: e.target.value })} />
              <datalist id="model-suggestions">{suggestions.map((m) => <option key={m} value={m} />)}</datalist>
            </div>
            <div className="field">
              <label>API key</label>
              <input className="input mono" type="password" autoComplete="off" value={draft.apiKey} placeholder="paste your key"
                     onChange={(e) => set({ apiKey: e.target.value })} />
              <span className="muted small">Kept in this tab only (sessionStorage) and sent to the backend with each request. It is never stored server-side.</span>
            </div>
            {status && <div className={`notice${status.ok ? " info" : ""}`}>{status.text}</div>}
          </>
        )}

        <div style={{ display: "flex", gap: 10, justifyContent: "flex-end", marginTop: 8 }}>
          {draft.mode === "byok" && <button className="btn" disabled={!draft.apiKey || testing} onClick={test}>{testing ? "Testing..." : "Test key"}</button>}
          {draft.mode === "byok" && access.apiKey && <button className="btn" onClick={() => { setAccess({ ...draft, apiKey: "", mode: "free" }); openAccess(false); }}>Forget key</button>}
          <button className="btn primary" onClick={() => { setAccess(draft); openAccess(false); }}>Save</button>
        </div>
      </div>
    </div>
  );
}
