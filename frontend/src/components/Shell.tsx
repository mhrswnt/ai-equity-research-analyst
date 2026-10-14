"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { AccessModal } from "./AccessModal";
import { useApp } from "@/lib/store";

export const NAV = [
  { href: "/", label: "Overview" },
  { href: "/qa", label: "Document Q&A" },
  { href: "/compare", label: "Compare companies" },
  { href: "/correlation", label: "Correlation" },
  { href: "/technical", label: "Technical analysis" },
  { href: "/backtest", label: "Backtest" },
  { href: "/strategy", label: "Strategy lab" },
  { href: "/research", label: "Web research" },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const { access, openAccess, theme, toggleTheme, documents, sessionId, endSession, backendError, ready } = useApp();
  const current = NAV.find((n) => n.href === path) ?? NAV[0];
  const model = access.mode === "byok" && access.apiKey ? `${access.provider}${access.model ? ` · ${access.model}` : ""}` : access.freeModel || "server default";

  return (
    <div className="shell">
      <aside className="side">
        <div className="brand">
          <div className="logo">Æ</div>
          <div><b>Analyst</b><small>equity research</small></div>
        </div>
        <nav className="nav">
          {NAV.map((n, i) => (
            <Link key={n.href} href={n.href} className={n.href === path ? "active" : ""}>
              <span className="n">{String(i).padStart(2, "0")}</span>{n.label}
            </Link>
          ))}
        </nav>
        <div className="workspace">
          <span className="eyebrow">Session</span>
          <span className="mono small">{sessionId ? `${sessionId.slice(0, 8)}…` : "none"}</span>
          <span className="muted small">{documents.length} docs · cleared on end or after idle</span>
          <button className="btn sm" onClick={() => endSession()}>End session &amp; wipe</button>
        </div>
      </aside>
      <div className="main">
        <header className="topbar">
          <h1>{current.label}</h1>
          <span className="sub">{DESCRIPTIONS[current.href]}</span>
          <button className={`pill${access.mode === "byok" && access.apiKey ? " byok" : ""}`} onClick={() => openAccess(true)} title="Model access">
            <span className="dot" />{access.mode === "byok" && access.apiKey ? "Own key" : "Free"} · <span className="mono">{model}</span>
          </button>
          <button className="btn" onClick={toggleTheme}>{theme === "dark" ? "Light mode" : "Dark mode"}</button>
        </header>
        <div className="content" style={path === "/qa" ? { padding: 0 } : undefined}>
          {backendError && (
            <div className="notice">Backend unavailable: {backendError} (set NEXT_PUBLIC_API_URL; default http://localhost:8000)</div>
          )}
          {ready ? children : <span className="muted"><span className="spinner" /> Connecting…</span>}
        </div>
      </div>
      <AccessModal />
    </div>
  );
}

const DESCRIPTIONS: Record<string, string> = {
  "/": "Everything runs on your backend: sessions, RAG, agents.",
  "/qa": "Ask questions across filings with page-level citations.",
  "/compare": "Pick two filings; get projected models side by side.",
  "/correlation": "Return correlation across NSE tickers.",
  "/technical": "Price summary, SMA crossover and RSI readouts.",
  "/backtest": "Test an SMA rule on historical prices vs buy & hold.",
  "/strategy": "Turn a research paper into an implementation plan and code.",
  "/research": "Research → write → review agents with a live feed.",
};
