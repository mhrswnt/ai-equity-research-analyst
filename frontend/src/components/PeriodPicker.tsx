"use client";
import { useState } from "react";
import { PERIOD_PRESETS, isValidPeriod, periodStart } from "@/lib/period";

/** Preset windows plus a custom value (e.g. 1000d, 18mo, 12w, ytd). Resolved start date is shown for transparency. */
export function PeriodPicker({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const isPreset = PERIOD_PRESETS.some((p) => p.value === value);
  const [custom, setCustom] = useState(isPreset ? "" : value);
  const start = periodStart(value);
  return (
    <div className="field">
      <label>Window</label>
      <div className="seg">
        {PERIOD_PRESETS.map((p) => (
          <button key={p.value} className={value === p.value ? "on" : ""} onClick={() => { setCustom(""); onChange(p.value); }}>{p.label}</button>
        ))}
      </div>
      <input className="input mono" style={{ marginTop: 8 }} value={custom} placeholder="custom: 1000d, 18mo, 12w, ytd"
             onChange={(e) => { setCustom(e.target.value); if (isValidPeriod(e.target.value)) onChange(e.target.value.trim()); }} />
      <span className="muted small">
        {start ? `From ${start.toISOString().slice(0, 10)} to today (daily bars)` : "Use a number plus d, w, mo or y — e.g. 1000d"}
      </span>
    </div>
  );
}
