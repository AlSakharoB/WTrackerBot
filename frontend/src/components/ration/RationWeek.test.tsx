import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchRationWeek } from "../../api/client";
import { RationWeek } from "./RationWeek";
import { weekDates } from "./weekDates";

vi.mock("../../api/client", async (original) => ({
  ...await original<typeof import("../../api/client")>(), fetchRationWeek: vi.fn(),
}));

describe("ration week", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchRationWeek).mockResolvedValue({
      week_start: "2026-09-07", week_end: "2026-09-13", today: "2026-09-13", timezone: "Europe/Moscow",
      days: weekDates("2026-09-13").map((date, index) => ({ date, entry_count: index === 0 ? 2 : 0, energy_kcal: index === 0 ? "120" : "0" })),
    });
  });

  function setup(value = "2026-09-13", initData = "signed") {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const onChange = vi.fn();
    const node = (date: string) => <QueryClientProvider client={client}><RationWeek value={date} today="2026-09-13" initData={initData} onChange={onChange} /></QueryClientProvider>;
    return { ...render(node(value)), node, onChange };
  }

  it("loads one summary, exposes filled days and reuses the cache within the week", async () => {
    const { rerender, node, onChange } = setup();
    const monday = await screen.findByRole("button", { name: /7 сентября.*2 записей, 120 ккал/ });
    expect(monday.querySelector("i")).toHaveClass("has-entries");
    expect(screen.getByRole("button", { name: /13 сентября.*сегодня/ })).toHaveAttribute("aria-pressed", "true");
    expect(screen.queryByRole("button", { name: "Предыдущий день" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Следующий день" })).not.toBeInTheDocument();
    fireEvent.click(monday);
    expect(onChange).toHaveBeenCalledWith("2026-09-07");
    rerender(node("2026-09-07"));
    await waitFor(() => expect(monday).toHaveAttribute("aria-pressed", "true"));
    expect(fetchRationWeek).toHaveBeenCalledTimes(1);
    rerender(node("2026-09-14"));
    await waitFor(() => expect(fetchRationWeek).toHaveBeenCalledTimes(2));
  });

  it("keeps date navigation available when the summary fails and allows retry", async () => {
    vi.mocked(fetchRationWeek).mockRejectedValueOnce(new Error("offline"));
    const { onChange } = setup();
    const retry = await screen.findByRole("button", { name: "Обновить данные недели" });
    fireEvent.keyDown(screen.getByRole("navigation", { name: "Дни недели" }), { key: "ArrowLeft" });
    expect(onChange).toHaveBeenCalledWith("2026-09-06");
    fireEvent.click(retry);
    await screen.findByRole("button", { name: /7 сентября.*2 записей/ });
    expect(fetchRationWeek).toHaveBeenCalledTimes(2);
  });

  it("does not send an unauthenticated query in browser preview", () => {
    setup("2026-09-13", "");
    expect(fetchRationWeek).not.toHaveBeenCalled();
    expect(screen.getByRole("navigation", { name: "Дни недели" }).children).toHaveLength(7);
  });

  it.each([["ArrowLeft", "2026-09-06"], ["PageUp", "2026-09-06"], ["ArrowRight", "2026-09-20"], ["PageDown", "2026-09-20"]])("switches one week using %s", (key, expected) => {
    const { onChange } = setup();
    fireEvent.keyDown(screen.getByRole("navigation", { name: "Дни недели" }), { key });
    expect(onChange).toHaveBeenCalledExactlyOnceWith(expected);
  });

  it("leaves browser keyboard shortcuts alone and returns to today on a date-heading tap", () => {
    const { onChange } = setup("2026-09-10");
    fireEvent.keyDown(screen.getByRole("navigation", { name: "Дни недели" }), { key: "ArrowLeft", altKey: true });
    expect(onChange).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTitle("Вернуться к сегодняшнему дню"));
    expect(onChange).toHaveBeenCalledExactlyOnceWith("2026-09-13");
  });
});
