import { describe, expect, it } from "vitest";
import { isValidPeriod, periodStart } from "./period";

const today = new Date(2026, 9, 3); // 3 Oct 2026
const iso = (d: Date | null) => d?.toISOString().slice(0, 10);

describe("periodStart", () => {
  it("resolves calendar windows like the backend", () => {
    expect(iso(periodStart("3mo", today))).toBe("2026-07-03");
    expect(iso(periodStart("6M", today))).toBe("2026-04-03");
    expect(iso(periodStart("1y", today))).toBe("2025-10-03");
    expect(iso(periodStart("1000d", today))).toBe("2024-01-07");
    expect(iso(periodStart("12w", today))).toBe("2026-07-11");
    expect(iso(periodStart("ytd", today))).toBe("2026-01-01");
  });
  it("rejects invalid input", () => {
    for (const bad of ["", "abc", "0d", "3", "1.5y"]) expect(isValidPeriod(bad)).toBe(false);
    expect(isValidPeriod(" 18mo ")).toBe(true);
  });
});
