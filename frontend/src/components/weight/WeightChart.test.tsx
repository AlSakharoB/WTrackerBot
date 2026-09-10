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

describe("WeightChart", () => {
  beforeAll(() => vi.stubGlobal("ResizeObserver", TestResizeObserver));
  afterAll(() => vi.unstubAllGlobals());

  it("renders one point with an accessible summary", async () => {
    render(<WeightChart points={POINTS.slice(0, 1)} targetWeight={null} timezone="Europe/Moscow" onSelect={vi.fn()} />);

    expect(screen.getByText(/Одно измерение: 82.4 кг/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: /82.4 кг/ })).toBeInTheDocument());
  });

  it("renders multiple selectable points", async () => {
    const onSelect = vi.fn();
    render(<WeightChart points={POINTS} targetWeight="75" timezone="Europe/Moscow" onSelect={onSelect} />);

    expect(screen.getByText(/2 измерений/)).toBeInTheDocument();
    const point = await screen.findByRole("button", { name: /81.75 кг/ });
    fireEvent.click(point);
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ id: "2" }));
  });
});
