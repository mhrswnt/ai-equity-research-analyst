"use client";
import { useRef, useState } from "react";
import { ErrorNotice, Spinner } from "@/components/ErrorNotice";
import { Markdown } from "@/components/Markdown";
import { client } from "@/lib/api";
import { useApp } from "@/lib/store";
import type { ResearchEvent, ResearchResult } from "@/lib/types";

export default function Research() {
  const { log } = useApp();
  const [topic, setTopic] = useState("");
  const [events, setEvents] = useState<ResearchEvent[]>([]);
  const [result, setResult] = useState<ResearchResult | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const abort = useRef<AbortController | null>(null);

  async function go() {
    setEvents([]); setResult(null); setError(null); setRunning(true);
    abort.current = new AbortController();
    try {
      await client.researchStream(topic, (e) => {
        if (e.type === "result") setResult(e);
        else setEvents((prev) => [...prev, e]);
      }, abort.current.signal);
      log("Web research", topic.length > 70 ? `${topic.slice(0, 70)}…` : topic);
    } catch (e) {
      if ((e as Error).name !== "AbortError") setError(e as Error);
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="grid two" style={{ gridTemplateColumns: "380px 1fr" }}>
      <div className="grid" style={{ alignContent: "start" }}>
        <div className="card">
          <div className="field"><label>Research topic</label>
            <textarea className="input" value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="HDFC Bank stock performance in May 2026: executive changes and analyst reactions" /></div>
          <div style={{ display: "flex", gap: 10 }}>
            <button className="btn primary" style={{ flex: 1 }} disabled={running || !topic.trim()} onClick={go}>{running ? "Researching…" : "Run research"}</button>
            {running && <button className="btn" onClick={() => abort.current?.abort()}>Stop</button>}
          </div>
          <p className="muted small">Research → Write → Review agents with web search. Needs your own API key.</p>
        </div>
        {(events.length > 0 || running) && (
          <div className="card">
            <h3>Live feed {running && <Spinner />}</h3>
            <div className="feed">
              {events.map((e, i) =>
                e.type === "agent" ? <div key={i} className="ev agent">▸ {e.agent}</div>
                : e.type === "output" ? <div key={i} className="ev">{e.content || <span className="muted">(tool step)</span>}{e.tools.length > 0 && <div className="muted mono">calls: {e.tools.join(", ")}</div>}</div>
                : e.type === "tool_result" ? <div key={i} className="ev tool"><span className="mono">{e.tool}</span> <span className="muted">{e.output}</span></div>
                : null)}
            </div>
          </div>
        )}
      </div>
      <div>
        <ErrorNotice error={error} />
        {!result && !running && !error && <div className="card muted">The final report and the reviewer&apos;s feedback appear here.</div>}
        {result && (
          <div className="grid">
            <div className="card"><div className="eyebrow" style={{ marginBottom: 10 }}>Report</div><Markdown>{result.report_content || "_No report was written._"}</Markdown></div>
            {result.review && <div className="card"><div className="eyebrow" style={{ marginBottom: 10 }}>Review</div><Markdown>{result.review}</Markdown></div>}
            {Object.keys(result.research_notes).length > 0 && (
              <details className="card"><summary className="muted small">Research notes ({Object.keys(result.research_notes).length})</summary>
                {Object.entries(result.research_notes).map(([k, v]) => <div key={k} style={{ marginTop: 12 }}><b>{k}</b><Markdown>{v}</Markdown></div>)}
              </details>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
