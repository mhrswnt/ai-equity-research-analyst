"use client";
import { useState } from "react";
import { AnalysisResult } from "@/components/AnalysisResult";
import { PeriodPicker } from "@/components/PeriodPicker";
import { TickerInput } from "@/components/TickerInput";
import { client } from "@/lib/api";
import { useApp } from "@/lib/store";
import { useRun } from "@/lib/useRun";

export default function Correlation() {
  const { log } = useApp();
  const [tickers, setTickers] = useState<string[]>(["DLF.NS", "LODHA.NS", "GODREJPROP.NS"]);
  const [period, setPeriod] = useState("6mo");
  const run = useRun(client.analysis);

  async function go() {
    const r = await run.run({ task: "compare", tickers, period });
    if (r) log("Correlation", `${tickers.join(", ")} · ${period}`);
  }

  return (
    <div className="grid two" style={{ gridTemplateColumns: "340px 1fr" }}>
      <div className="card">
        <div className="field"><label>Tickers (NSE, at least 2)</label><TickerInput value={tickers} onChange={setTickers} /></div>
        <PeriodPicker value={period} onChange={setPeriod} />
        <button className="btn primary" style={{ width: "100%" }} disabled={tickers.length < 2 || run.loading} onClick={go}>{run.loading ? "Running…" : "Compute correlation"}</button>
      </div>
      <AnalysisResult {...run} hint="Normalized returns, correlation matrix and the most correlated pair appear here." />
    </div>
  );
}
