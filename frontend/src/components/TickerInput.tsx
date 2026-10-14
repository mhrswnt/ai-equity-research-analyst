"use client";
import { useState } from "react";

/** NSE tickers: auto-uppercases and appends .NS when no exchange suffix is given. */
export const normalizeTicker = (raw: string) => {
  const t = raw.trim().toUpperCase();
  return t && !t.includes(".") ? `${t}.NS` : t;
};

export function TickerInput({ value, onChange, placeholder = "Add ticker, e.g. TCS" }: {
  value: string[]; onChange: (v: string[]) => void; placeholder?: string;
}) {
  const [text, setText] = useState("");
  const add = () => {
    const t = normalizeTicker(text);
    if (t && !value.includes(t)) onChange([...value, t]);
    setText("");
  };
  return (
    <div>
      <div className="chips" style={{ marginBottom: 8 }}>
        {value.map((t) => <span key={t} className="chip">{t}<button aria-label={`Remove ${t}`} onClick={() => onChange(value.filter((x) => x !== t))}>×</button></span>)}
      </div>
      <input className="input" value={text} placeholder={placeholder} onChange={(e) => setText(e.target.value)}
             onKeyDown={(e) => { if (e.key === "Enter" || e.key === ",") { e.preventDefault(); add(); } }} onBlur={add} />
    </div>
  );
}
