"use client";
import { useState } from "react";
import { ErrorNotice, Spinner } from "@/components/ErrorNotice";
import { Library } from "@/components/Library";
import { Markdown } from "@/components/Markdown";
import { client } from "@/lib/api";
import { useApp } from "@/lib/store";
import { useRun } from "@/lib/useRun";

export default function Strategy() {
  const { selected, documents, log } = useApp();
  const [libraries, setLibraries] = useState("pandas, numpy, and statsmodels");
  const [instruction, setInstruction] = useState("");
  const [topK, setTopK] = useState(8);
  const [copied, setCopied] = useState(false);
  const run = useRun(client.strategy);
  const docId = selected[0];
  const doc = documents.find((d) => d.id === docId);
  const res = run.result;

  async function go() {
    const r = await run.run({ document_id: docId, libraries, top_k: topK, ...(instruction.trim() ? { instruction } : {}) });
    if (r) log("Strategy lab", `Parsed “${doc?.name}”`);
  }

  return (
    <div className="grid two" style={{ gridTemplateColumns: "340px 1fr" }}>
      <div className="card">
        <h3>Research paper</h3>
        <Library mode="single" max={1} />
        <div className="field" style={{ marginTop: 14 }}><label>Libraries for the generated code</label><input className="input" value={libraries} onChange={(e) => setLibraries(e.target.value)} /></div>
        <div className="field"><label>Retrieved passages per query: {topK}</label><input type="range" min={2} max={20} value={topK} onChange={(e) => setTopK(+e.target.value)} /></div>
        <div className="field"><label>Extra instruction (optional)</label><textarea className="input" value={instruction} onChange={(e) => setInstruction(e.target.value)} placeholder="Use a 60-day lookback and 10 bps costs…" /></div>
        <button className="btn primary" style={{ width: "100%" }} disabled={!docId || run.loading} onClick={go}>{run.loading ? "Generating…" : "Generate plan & code"}</button>
        <p className="muted small">Needs your own API key. The agent reads the paper through the shared retriever.</p>
      </div>
      <div>
        <ErrorNotice error={run.error} />
        {run.loading && <div className="card"><Spinner label="Extracting the strategy and writing code…" /></div>}
        {!res && !run.loading && <div className="card muted">The implementation plan and Python code appear here.</div>}
        {res && (
          <div className="grid">
            {res.plan && <div className="card"><div className="eyebrow" style={{ marginBottom: 10 }}>Implementation plan</div><Markdown>{res.plan}</Markdown></div>}
            <div className="card">
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 10 }}>
                <span className="eyebrow">Generated code</span>
                <button className="btn sm" onClick={async () => { await navigator.clipboard.writeText(res.code); setCopied(true); setTimeout(() => setCopied(false), 1500); }}>{copied ? "Copied" : "Copy"}</button>
              </div>
              <pre className="code">{res.code}</pre>
            </div>
            <details className="card"><summary className="muted small">Raw agent response</summary><pre className="code" style={{ marginTop: 12, whiteSpace: "pre-wrap" }}>{res.raw}</pre></details>
          </div>
        )}
      </div>
    </div>
  );
}
