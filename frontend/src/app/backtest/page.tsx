"use client";
import { useState } from "react";
import { AnalysisResult } from "@/components/AnalysisResult";
import { PeriodPicker } from "@/components/PeriodPicker";
import { normalizeTicker } from "@/components/TickerInput";
import { client } from "@/lib/api";
import { useApp } from "@/lib/store";
import { useRun } from "@/lib/useRun";

export default function Backtest() {
  const { log } = useApp();
  const [ticker, setTicker] = useState("SURYAROSNI");
  const [period, setPeriod] = useState("1y");
  const [sma, setSma] = useState(20);
  const run = useRun(client.analysis);

  async function go() {
    const t = normalizeTicker(ticker);
    const r = await run.run({ task: "backtest", ticker: t, period, sma_window: sma });
    if (r) log("Backtest", `SMA ${sma} on ${t} · ${period}`);
  }

  return (
    <div className="grid two" style={{ gridTemplateColumns: "340px 1fr" }}>
      <div className="card">
        <div className="eyebrow">Strategy</div>
        <h3 style={{ marginTop: 4 }}>SMA {sma} trend filter</h3>
        <p className="muted small">Buy when price crosses above the SMA, sell when it crosses below; compared to buy &amp; hold.</p>
        <div className="field"><label>Ticker (NSE)</label><input className="input mono" value={ticker} onChange={(e) => setTicker(e.target.value)} /></div>
        <PeriodPicker value={period} onChange={setPeriod} />
        <div className="field"><label>SMA window: {sma}d</label><input type="range" min={5} max={200} value={sma} onChange={(e) => setSma(+e.target.value)} /></div>
        <button className="btn primary" style={{ width: "100%" }} disabled={run.loading || !ticker.trim()} onClick={go}>{run.loading ? "Running…" : "Run backtest →"}</button>
      </div>
      <AnalysisResult {...run} hint="Strategy vs buy-and-hold returns appear here." />
    </div>
  );
}
