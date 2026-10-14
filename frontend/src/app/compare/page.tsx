"use client";
import { ErrorNotice, Spinner } from "@/components/ErrorNotice";
import { Library } from "@/components/Library";
import { Markdown } from "@/components/Markdown";
import { client } from "@/lib/api";
import { useApp } from "@/lib/store";
import { useRun } from "@/lib/useRun";
import type { CompareMemo, FinancialModel } from "@/lib/types";

const fmt = (n: number, unit = "") => `${n.toLocaleString("en-IN", { maximumFractionDigits: 1 })}${unit}`;
const ROWS: Array<{ label: string; get: (m: FinancialModel) => number; unit: string; prefix?: string }> = [
  { label: "Projected revenue (next yr)", get: (m) => m.revenue_projection, unit: " cr", prefix: "₹" },
  { label: "Revenue growth", get: (m) => m.growth_rate, unit: "%" },
  { label: "Enterprise value estimate", get: (m) => m.valuation_estimate, unit: " cr", prefix: "₹" },
];

export default function Compare() {
  const { selected, documents, log } = useApp();
  const cmp = useRun(client.compare);
  const [a, b] = selected;
  const ready = selected.length === 2;
  const memo: CompareMemo | null = cmp.result;

  async function run() {
    const res = await cmp.run(a, b);
    if (res) log("Compare", `${res.company_a_name || "A"} vs ${res.company_b_name || "B"}`);
  }

  return (
    <div className="grid two" style={{ gridTemplateColumns: "320px 1fr" }}>
      <div className="card">
        <h3>Choose two filings</h3>
        <Library max={2} />
        <button className="btn primary" style={{ width: "100%", marginTop: 14 }} disabled={!ready || cmp.loading} onClick={run}>
          {cmp.loading ? "Extracting & modelling…" : "Compare"}
        </button>
        {!ready && <p className="muted small">Select exactly two documents ({selected.length}/2).</p>}
        <p className="muted small">Uses LlamaExtract to pull financials, then models both companies with the assumptions file. Needs your own API key.</p>
      </div>
      <div>
        <ErrorNotice error={cmp.error} />
        {cmp.loading && <div className="card"><Spinner label="Parsing both documents and building models (can take a minute)…" /></div>}
        {!memo && !cmp.loading && <div className="card muted">Results appear here.{documents.length < 2 && " Upload two filings first."}</div>}
        {memo && (
          <div className="grid">
            <div className="card" style={{ padding: 0, overflow: "hidden" }}>
              <table className="table">
                <thead><tr><th>Metric</th><th>{memo.company_a_name || "Company A"}</th><th>{memo.company_b_name || "Company B"}</th></tr></thead>
                <tbody>
                  {ROWS.map((r) => {
                    const [x, y] = [r.get(memo.company_a_model), r.get(memo.company_b_model)];
                    return (
                      <tr key={r.label}>
                        <td>{r.label}</td>
                        <td className={x > y ? "best" : ""}>{r.prefix}{fmt(x, r.unit)}</td>
                        <td className={y > x ? "best" : ""}>{r.prefix}{fmt(y, r.unit)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div className="grid" style={{ gridTemplateColumns: "1fr 1fr" }}>
              <div className="card">
                <h3>Revenue growth</h3>
                {[[memo.company_a_name || "A", memo.company_a_model.growth_rate, "var(--accent)"], [memo.company_b_name || "B", memo.company_b_model.growth_rate, "var(--blue)"]].map(([n, g, color]) => {
                  const max = Math.max(Math.abs(memo.company_a_model.growth_rate), Math.abs(memo.company_b_model.growth_rate), 1);
                  return (
                    <div className="bar-row" key={n as string}>
                      <span className="mono small">{n as string}</span>
                      <div className="bar"><i style={{ width: `${(Math.abs(g as number) / max) * 100}%`, background: color as string }} /></div>
                      <span className={`mono small ${(g as number) >= 0 ? "best" : ""}`}>{(g as number) >= 0 ? "+" : ""}{g as number}%</span>
                    </div>
                  );
                })}
              </div>
              <div className="card">
                <h3>Model notes</h3>
                <p className="small"><b>{memo.company_a_name || "A"}:</b> {memo.company_a_model.summary}</p>
                <p className="small"><b>{memo.company_b_name || "B"}:</b> {memo.company_b_model.summary}</p>
              </div>
            </div>
            <div className="card">
              <h3>Analyst takeaways</h3>
              <Markdown>{memo.comparative_analysis.comparative_analysis}</Markdown>
              <h3 style={{ marginTop: 18 }}>Recommendation</h3>
              <Markdown>{memo.comparative_analysis.overall_recommendation}</Markdown>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
