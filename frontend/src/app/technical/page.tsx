"use client";
import { useState } from "react";
import { AnalysisResult } from "@/components/AnalysisResult";
import { PeriodPicker } from "@/components/PeriodPicker";
import { normalizeTicker } from "@/components/TickerInput";
import { client } from "@/lib/api";
import { useApp } from "@/lib/store";
import { useRun } from "@/lib/useRun";
import type { AnalysisParams } from "@/lib/types";

type Mode = "technical" | "price_summary" | "custom";

export default function Technical() {
  const { log } = useApp();
  const [mode, setMode] = useState<Mode>("technical");
  const [ticker, setTicker] = useState("RELIANCE");
  const [period, setPeriod] = useState("6mo");
  const [shortW, setShortW] = useState(20);
  const [longW, setLongW] = useState(50);
  const [rsi, setRsi] = useState(14);
  const [prompt, setPrompt] = useState("");
  const run = useRun(client.analysis);

  async function go() {
    const t = normalizeTicker(ticker);
    const params: AnalysisParams =
      mode === "technical" ? { task: "technical", ticker: t, period, short_window: shortW, long_window: longW, rsi_period: rsi }
      : mode === "price_summary" ? { task: "price_summary", ticker: t, period }
      : { task: "custom", prompt };
    const r = await run.run(params);
    if (r) log("Technical analysis", mode === "custom" ? prompt.slice(0, 70) : `${mode.replace("_", " ")} · ${t}`);
  }

  return (
    <div className="grid two" style={{ gridTemplateColumns: "340px 1fr" }}>
      <div className="card">
        <div className="seg" style={{ marginBottom: 16 }}>
          <button className={mode === "technical" ? "on" : ""} onClick={() => setMode("technical")}>Technical</button>
          <button className={mode === "price_summary" ? "on" : ""} onClick={() => setMode("price_summary")}>Price summary</button>
          <button className={mode === "custom" ? "on" : ""} onClick={() => setMode("custom")}>Custom ⚿</button>
        </div>
        {mode === "custom" ? (
          <div className="field"><label>Instruction for the coding agent (needs your own key)</label>
            <textarea className="input" value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="Fetch 1y of TCS.NS and plot the 30-day rolling volatility…" /></div>
        ) : (
          <>
            <div className="field"><label>Ticker (NSE)</label><input className="input mono" value={ticker} onChange={(e) => setTicker(e.target.value)} /></div>
            <PeriodPicker value={period} onChange={setPeriod} />
            {mode === "technical" && (
              <>
                <div className="field"><label>Fast SMA: {shortW}d</label><input type="range" min={5} max={60} value={shortW} onChange={(e) => setShortW(+e.target.value)} /></div>
                <div className="field"><label>Slow SMA: {longW}d</label><input type="range" min={20} max={200} value={longW} onChange={(e) => setLongW(+e.target.value)} /></div>
                <div className="field"><label>RSI period: {rsi}</label><input type="range" min={5} max={30} value={rsi} onChange={(e) => setRsi(+e.target.value)} /></div>
              </>
            )}
          </>
        )}
        <button className="btn primary" style={{ width: "100%" }} disabled={run.loading || (mode === "custom" ? !prompt.trim() : !ticker.trim())} onClick={go}>{run.loading ? "Running…" : "Run analysis"}</button>
      </div>
      <AnalysisResult {...run} hint="Signals, indicators and a plain-language readout appear here." />
    </div>
  );
}
