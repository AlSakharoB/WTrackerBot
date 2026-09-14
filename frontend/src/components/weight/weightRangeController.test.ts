import { describe, expect, it } from "vitest";

import {
  gestureDirection,
  inclusiveDayCount,
  latestWeightRange,
  matchingWeightPreset,
  normalizeWeightRange,
  panWeightRange,
  shiftWeightRange,
  zoomWeightRange,
} from "./weightRangeController";

const TODAY = "2026-09-14";
const CURRENT = { from: "2026-08-16", to: TODAY };

describe("weightRangeController", () => {
  it("pans right into history and left toward today", () => {
    expect(panWeightRange(CURRENT, 150, 300, TODAY)).toEqual({ from: "2026-08-01", to: "2026-08-30" });
    const historical = { from: "2026-07-01", to: "2026-07-30" };
    expect(panWeightRange(historical, -150, 300, TODAY)).toEqual({ from: "2026-07-16", to: "2026-08-14" });
  });

  it("locks horizontal gestures without stealing vertical scroll", () => {
    expect(gestureDirection(4, 3)).toBe("pending");
    expect(gestureDirection(13, 8)).toBe("horizontal");
    expect(gestureDirection(8, 13)).toBe("vertical");
  });

  it("zooms in and out around the midpoint", () => {
    const zoomedIn = zoomWeightRange(CURRENT, 2, 0.5, TODAY);
    const zoomedOut = zoomWeightRange(zoomedIn, 0.5, 0.5, TODAY);

    expect(inclusiveDayCount(zoomedIn)).toBe(15);
    expect(zoomedIn).toEqual({ from: "2026-08-24", to: "2026-09-07" });
    expect(zoomedOut).toEqual(CURRENT);
  });

  it("keeps an off-center pinch anchor stable", () => {
    const zoomed = zoomWeightRange(CURRENT, 2, 0.25, TODAY);
    expect(zoomed).toEqual({ from: "2026-08-19", to: "2026-09-02" });
  });

  it("clamps zoom and normalization to 7...365 days", () => {
    expect(inclusiveDayCount(zoomWeightRange(CURRENT, 100, 0.5, TODAY))).toBe(7);
    expect(inclusiveDayCount(zoomWeightRange(CURRENT, 0.01, 0.5, TODAY))).toBe(365);
    expect(inclusiveDayCount(normalizeWeightRange({ from: "2026-09-14", to: "2026-09-14" }, TODAY))).toBe(7);
    expect(inclusiveDayCount(normalizeWeightRange({ from: "2024-01-01", to: TODAY }, TODAY))).toBe(365);
  });

  it("never shifts beyond the user's local today", () => {
    expect(shiftWeightRange({ from: "2026-07-01", to: "2026-07-30" }, 100, TODAY)).toEqual(CURRENT);
    expect(normalizeWeightRange({ from: "2026-09-01", to: "2026-10-01" }, TODAY).to).toBe(TODAY);
  });

  it("only matches an exact preset", () => {
    expect(matchingWeightPreset(30)).toBe(30);
    expect(matchingWeightPreset(29)).toBeNull();
    expect(matchingWeightPreset(42)).toBeNull();
    expect(latestWeightRange(42, TODAY)).toEqual({ from: "2026-08-04", to: TODAY });
  });
});
