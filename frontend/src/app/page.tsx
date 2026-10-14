"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Library } from "@/components/Library";
import { client } from "@/lib/api";
import { useApp } from "@/lib/store";
import type { Health, TaskInfo } from "@/lib/types";

const CARDS = [
  { href: "/qa", n: "01", title: "Document Q&A", ids: ["qa"], text: "Ask questions across filings with page-level citations." },
  { href: "/compare", n: "02", title: "Compare companies", ids: ["compare_memo"], text: "Pick two filings; get projected models and a recommendation side by side." },
  { href: "/correlation", n: "03", title: "Correlation", ids: ["analysis_compare"], text: "Normalized returns and correlations across NSE tickers." },
  { href: "/technical", n: "04", title: "Technical analysis", ids: ["analysis_technical", "analysis_price_summary", "analysis_custom"], text: "SMA crossover, RSI and price summaries, plus custom analysis." },
  { href: "/backtest", n: "05", title: "Backtest", ids: ["analysis_backtest"], text: "Test an SMA rule against buy & hold." },
  { href: "/strategy", n: "06", title: "Strategy lab", ids: ["strategy"], text: "Turn a research paper into an implementation plan and Python code." },
  { href: "/research", n: "07", title: "Web research", ids: ["research"], text: "Research, write and review agents produce a sourced report." },
];

function greeting() {
  const h = new Date().getHours();
  return h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

export default function Overview() {
  const { documents, activity, sessionId } = useApp();
  const [tasks, setTasks] = useState<TaskInfo[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  useEffect(() => {
    client.tasks().then(setTasks).catch(() => undefined);
    client.health().then(setHealth).catch(() => undefined);
  }, [sessionId]);
  const freeAllowed = (ids: string[]) => ids.every((id) => tasks.find((t) => t.id === id)?.free_allowed);

  return (
    <>
      <div className="hero">
        <h2>{greeting()}.</h2>
        <p>{documents.length ? `${documents.length} document${documents.length > 1 ? "s" : ""} indexed in this session.` : "Upload a filing to get started, or run a ticker analysis."}</p>
      </div>
      <div className="grid cards">
        {CARDS.map((c) => (
          <Link key={c.href} href={c.href} className="card task-card">
            <span className="n">{c.n}</span>
            <h4>{c.title}</h4>
            <p>{c.text}</p>
            {tasks.length > 0 && (
              <span className={`badge${freeAllowed(c.ids) ? "" : " key"}`} style={{ alignSelf: "flex-start" }}>
                {c.ids.every((id) => freeAllowed([id])) ? "free tier" : c.ids.some((id) => freeAllowed([id])) ? "free + own key" : "needs own key"}
              </span>
            )}
          </Link>
        ))}
      </div>
      <div className="grid two" style={{ marginTop: 24 }}>
        <div className="card">
          <h3>Library</h3>
          <Library />
        </div>
        <div className="grid">
          <div className="card">
            <h3>Recent activity</h3>
            {activity.length === 0 && <p className="muted small">Nothing yet. Runs in this session appear here.</p>}
            <div className="list">
              {activity.slice(0, 6).map((a) => (
                <div className="row" key={a.id} style={{ flexDirection: "column", alignItems: "flex-start", gap: 2 }}>
                  <span>{a.summary}</span>
                  <span className="muted small mono">{a.screen} · {new Date(a.at).toLocaleTimeString()}</span>
                </div>
              ))}
            </div>
          </div>
          <div className="card">
            <h3>Backend</h3>
            {!health ? <p className="muted small">Not reachable.</p> : (
              <div className="small">
                <p style={{ margin: "0 0 8px" }}><span className="badge">status</span> {health.status}</p>
                <div className="chips" style={{ marginBottom: 8 }}>
                  {Object.entries(health.keys_configured).map(([k, v]) => (
                    <span key={k} className="chip" style={{ color: v ? "var(--green)" : "var(--red)" }}>{k} {v ? "✓" : "✗"}</span>
                  ))}
                </div>
                <div className="muted">Free models: {health.free_models.join(", ")}</div>
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
