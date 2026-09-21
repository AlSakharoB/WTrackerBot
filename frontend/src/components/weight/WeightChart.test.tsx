import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterAll, beforeAll, describe, expect, it, vi } from "vitest";

import type { WeightChartPoint } from "../../api/client";
import { WeightChart } from "./WeightChart";

const POINTS: WeightChartPoint[] = [
  {
    id: "1",
    weight_kg: "82.4",
    measured_at: "2026-09-01T05:00:00Z",
    note: null,
    updated_at: "2026-09-01T05:00:00Z",
    moving_average_7d_kg: null,
  },
  {
    id: "2",
    weight_kg: "81.75",
    measured_at: "2026-09-10T17:00:00Z",
    note: "После тренировки",
    updated_at: "2026-09-10T17:00:00Z",
    moving_average_7d_kg: "81.75",
  },
];

const RANGE = { from: "2026-08-16", to: "2026-09-14" };

class TestResizeObserver {
  public constructor(private readonly callback: ResizeObserverCallback) {}

  public observe(target: Element) {
    const contentRect = {
      width: 600,
      height: 320,
      top: 0,
      right: 600,
      bottom: 320,
      left: 0,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    } as DOMRectReadOnly;
    this.callback([{ target, contentRect } as ResizeObserverEntry], this as unknown as ResizeObserver);
  }

  public unobserve() {}
  public disconnect() {}
}

function renderChart(overrides: Partial<React.ComponentProps<typeof WeightChart>> = {}) {
  const props: React.ComponentProps<typeof WeightChart> = {
    points: POINTS,
    targetWeight: "75",
    timezone: "Europe/Moscow",
    range: RANGE,
    today: "2026-09-14",
    onRangeCommit: vi.fn(),
    onSelect: vi.fn(),
    ...overrides,
  };
  const result = render(<WeightChart {...props} />);
  const chart = screen.getByRole("group", { name: "Интерактивный график изменения веса" });
  vi.spyOn(chart, "getBoundingClientRect").mockReturnValue({
    width: 300,
    height: 300,
    top: 0,
    right: 300,
    bottom: 300,
    left: 0,
    x: 0,
    y: 0,
    toJSON: () => ({}),
  });
  return { ...result, chart, props };
}

describe("WeightChart", () => {
  beforeAll(() => vi.stubGlobal("ResizeObserver", TestResizeObserver));
  afterAll(() => vi.unstubAllGlobals());

  it("renders one point with an accessible summary", async () => {
    renderChart({ points: POINTS.slice(0, 1), targetWeight: null });

    expect(screen.getByText(/Одно измерение: 82.4 кг/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: /82.4 кг/ })).toBeInTheDocument());
  });

  it("opens a mobile-safe tooltip before editing a point", async () => {
    const onSelect = vi.fn();
    renderChart({ onSelect });

    const point = await screen.findByRole("button", { name: /81.75 кг/ });
    fireEvent.click(point);
    expect(onSelect).not.toHaveBeenCalled();
    expect(screen.getByRole("status")).toHaveTextContent("81,75 кг");

    fireEvent.pointerDown(document.body);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();

    fireEvent.click(await screen.findByRole("button", { name: /81.75 кг/ }));
    expect(screen.getByRole("status")).toHaveTextContent("81,75 кг");

    fireEvent.click(screen.getByRole("button", { name: "Изменить" }));
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ id: "2" }));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("commits one mouse pan after pointerup and not during moves", () => {
    const onRangeCommit = vi.fn();
    const { chart } = renderChart({ onRangeCommit });

    fireEvent.pointerDown(chart, { pointerId: 1, pointerType: "mouse", button: 0, clientX: 120, clientY: 100 });
    fireEvent.pointerMove(chart, { pointerId: 1, pointerType: "mouse", clientX: 180, clientY: 102 });
    fireEvent.pointerMove(chart, { pointerId: 1, pointerType: "mouse", clientX: 220, clientY: 103 });
    expect(onRangeCommit).not.toHaveBeenCalled();
    fireEvent.pointerUp(chart, { pointerId: 1, pointerType: "mouse", clientX: 220, clientY: 103 });

    expect(onRangeCommit).toHaveBeenCalledOnce();
    expect(onRangeCommit).toHaveBeenCalledWith({ from: "2026-08-06", to: "2026-09-04" });
    fireEvent.click(screen.getByRole("button", { name: /81.75 кг/ }));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /81.75 кг/ }));
    expect(screen.getByRole("status")).toHaveTextContent("81,75 кг");
  });

  it("leaves a vertical one-pointer gesture to page scrolling", () => {
    const onRangeCommit = vi.fn();
    const { chart } = renderChart({ onRangeCommit });

    fireEvent.pointerDown(chart, { pointerId: 1, pointerType: "touch", button: 0, clientX: 120, clientY: 80 });
    fireEvent.pointerMove(chart, { pointerId: 1, pointerType: "touch", clientX: 125, clientY: 130 });
    fireEvent.pointerUp(chart, { pointerId: 1, pointerType: "touch", clientX: 125, clientY: 130 });

    expect(onRangeCommit).not.toHaveBeenCalled();
  });

  it("commits one pinch zoom around two active pointers", () => {
    const onRangeCommit = vi.fn();
    const { chart } = renderChart({ onRangeCommit });

    fireEvent.pointerDown(chart, { pointerId: 1, pointerType: "touch", button: 0, clientX: 75, clientY: 100 });
    fireEvent.pointerDown(chart, { pointerId: 2, pointerType: "touch", button: 0, clientX: 225, clientY: 100 });
    fireEvent.pointerMove(chart, { pointerId: 2, pointerType: "touch", clientX: 275, clientY: 100 });
    expect(onRangeCommit).not.toHaveBeenCalled();
    fireEvent.pointerUp(chart, { pointerId: 2, pointerType: "touch", clientX: 275, clientY: 100 });

    expect(onRangeCommit).toHaveBeenCalledOnce();
    expect(onRangeCommit).toHaveBeenCalledWith({ from: "2026-08-20", to: "2026-09-11" });
  });

  it("cancels a gesture and cleans up safely on unmount", () => {
    const onRangeCommit = vi.fn();
    const { chart, unmount } = renderChart({ onRangeCommit });

    fireEvent.pointerDown(chart, { pointerId: 7, pointerType: "touch", button: 0, clientX: 100, clientY: 100 });
    fireEvent.pointerMove(chart, { pointerId: 7, pointerType: "touch", clientX: 160, clientY: 100 });
    fireEvent.pointerCancel(chart, { pointerId: 7, pointerType: "touch" });
    expect(onRangeCommit).not.toHaveBeenCalled();
    expect(() => unmount()).not.toThrow();
  });
});
