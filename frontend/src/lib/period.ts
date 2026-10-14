/** Mirrors backend `resolve_period`: calendar-based windows ('3mo', '1y', '1000d', '12w', 'ytd'). */
const RE = /^\s*(\d+)\s*(d|w|wk|mo|m|y)\s*$/i;

export const PERIOD_PRESETS = [
  { label: "1M", value: "1mo" }, { label: "3M", value: "3mo" }, { label: "6M", value: "6mo" },
  { label: "1Y", value: "1y" }, { label: "3Y", value: "3y" }, { label: "5Y", value: "5y" },
];

export function periodStart(period: string, today = new Date()): Date | null {
  const text = period.trim().toLowerCase();
  const d = new Date(Date.UTC(today.getFullYear(), today.getMonth(), today.getDate()));
  if (text === "ytd") return new Date(Date.UTC(today.getFullYear(), 0, 1));
  const m = RE.exec(text);
  if (!m || Number(m[1]) < 1) return null;
  const n = Number(m[1]);
  switch (m[2].toLowerCase()) {
    case "d": d.setUTCDate(d.getUTCDate() - n); break;
    case "w": case "wk": d.setUTCDate(d.getUTCDate() - 7 * n); break;
    case "mo": case "m": d.setUTCMonth(d.getUTCMonth() - n); break;
    default: d.setUTCFullYear(d.getUTCFullYear() - n);
  }
  return d;
}

export const isValidPeriod = (p: string) => periodStart(p) !== null;
