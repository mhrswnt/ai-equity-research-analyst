"use client";
import { ErrorNotice, Spinner } from "./ErrorNotice";
import { Markdown } from "./Markdown";
import type { AnalysisResponse } from "@/lib/types";

export function AnalysisResult({ loading, error, result, hint }: {
  loading: boolean; error: Error | null; result: AnalysisResponse | null; hint: string;
}) {
  return (
    <div>
      <ErrorNotice error={error} />
      {loading && <div className="card"><Spinner label="Agent is writing and running code (can take a minute)…" /></div>}
      {!loading && !result && !error && <div className="card muted">{hint}</div>}
      {result && !loading && (
        <div className="grid">
          <div className="card"><div className="eyebrow" style={{ marginBottom: 10 }}>Result</div><Markdown>{result.result}</Markdown></div>
          <details className="card"><summary className="muted small">Prompt sent to the agent</summary><pre className="code" style={{ marginTop: 12, whiteSpace: "pre-wrap" }}>{result.prompt}</pre></details>
        </div>
      )}
    </div>
  );
}
