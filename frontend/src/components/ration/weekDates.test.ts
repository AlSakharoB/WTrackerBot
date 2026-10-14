import { describe, expect, it } from "vitest";

import { weekDates } from "./weekDates";

describe("ration week dates", () => {
  it("uses Monday through Sunday even across a year boundary", () => {
    expect(weekDates("2026-01-01")).toEqual([
      "2025-12-29", "2025-12-30", "2025-12-31", "2026-01-01",
      "2026-01-02", "2026-01-03", "2026-01-04",
    ]);
  });

  it("includes leap day", () => {
    expect(weekDates("2024-02-29")).toContain("2024-02-29");
    expect(weekDates("2024-02-29")).toHaveLength(7);
  });

  it("keeps the same week for Sunday and Monday despite DST", () => {
    expect(weekDates("2026-03-29")).toEqual(weekDates("2026-03-23"));
    expect(weekDates("2026-03-30")[0]).toBe("2026-03-30");
  });
});
