import { renderHook } from "@testing-library/react";
import { animate } from "motion/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useTweenNumber } from "./useTweenNumber";

const state = vi.hoisted(() => ({ reduced: false, stop: vi.fn() }));
vi.mock("motion/react", async (original) => ({
  ...await original<typeof import("motion/react")>(),
  animate: vi.fn(() => ({ stop: state.stop })),
  useReducedMotion: () => state.reduced,
}));

describe("nutrition number transitions", () => {
  beforeEach(() => { vi.clearAllMocks(); state.reduced = false; });

  it("starts at the actual value and only animates a changed total", () => {
    const { result, rerender, unmount } = renderHook(({ value }) => useTweenNumber(value), { initialProps: { value: 120 } });
    expect(result.current.get()).toBe(120);
    expect(animate).not.toHaveBeenCalled();
    rerender({ value: 120 });
    expect(animate).not.toHaveBeenCalled();
    rerender({ value: 140 });
    expect(animate).toHaveBeenCalledTimes(1);
    rerender({ value: 160 });
    expect(state.stop).toHaveBeenCalledTimes(1);
    unmount();
    expect(state.stop).toHaveBeenCalledTimes(2);
  });

  it("updates immediately when reduced motion is enabled", () => {
    state.reduced = true;
    const { result, rerender } = renderHook(({ value }) => useTweenNumber(value), { initialProps: { value: 120 } });
    rerender({ value: 140 });
    expect(result.current.get()).toBe(140);
    expect(animate).not.toHaveBeenCalled();
  });
});
