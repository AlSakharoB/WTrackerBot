import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../../api/client";
import { ToastProvider } from "../ui";
import { RationAddSheet } from "./RationAddSheet";
import { RationEntrySheet } from "./RationEntrySheet";

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return {
    ...actual,
    fetchRationSources: vi.fn(),
    createRationEntry: vi.fn(),
    updateRationEntry: vi.fn(),
    copyRationEntry: vi.fn(),
    deleteRationEntry: vi.fn(),
  };
});

const source: api.RationSource = {
  id: "ingredient-1",
  type: "ingredient",
  name: "Йогурт натуральный",
  default_grams: "100",
  nutrition_per_100g: {
    energy_kcal: "62",
    protein_g: "4",
    fat_g: "2.5",
    carbs_g: "5.9",
  },
  usage_count: 2,
  last_used_at: "2026-09-12T08:00:00Z",
};

const entry: api.RationEntry = {
  id: "entry-1",
  type: "ingredient",
  source_id: source.id,
  source_available: true,
  source_name: source.name,
  grams: "100",
  meal_type: "breakfast",
  nutrition: source.nutrition_per_100g,
  created_at: "2026-09-13T08:00:00Z",
  updated_at: "2026-09-13T08:00:00Z",
};

function renderFlow(node: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <ToastProvider>{node}</ToastProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

describe("ration entry flows", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.fetchRationSources).mockResolvedValue([source]);
  });

  it("disables repeated creation while the first request is pending", async () => {
    let resolveCreate: (value: api.RationEntry) => void = () => undefined;
    vi.mocked(api.createRationEntry).mockReturnValue(new Promise((resolve) => { resolveCreate = resolve; }));
    const onSaved = vi.fn();

    renderFlow(
      <RationAddSheet
        open
        date="2026-09-13"
        initialMeal="breakfast"
        format="automatic"
        initData="test-init-data"
        authorized
        formatValue={(value) => String(value)}
        onClose={vi.fn()}
        onSaved={onSaved}
      />,
    );

    fireEvent.click(await screen.findByRole("button", { name: /Йогурт натуральный/ }));
    fireEvent.click(screen.getByRole("button", { name: "Увеличить количество на 10 грамм" }));
    expect(screen.getByLabelText("Количество, г")).toHaveValue("110");

    const submit = screen.getByRole("button", { name: "Добавить в завтрак" });
    fireEvent.click(submit);
    fireEvent.click(submit);

    await waitFor(() => expect(api.createRationEntry).toHaveBeenCalledOnce());
    expect(screen.getByRole("button", { name: "Добавляем..." })).toBeDisabled();
    const [, date, payload, idempotencyKey] = vi.mocked(api.createRationEntry).mock.calls[0];
    expect(date).toBe("2026-09-13");
    expect(payload).toMatchObject({ source_id: source.id, grams: "110", meal_type: "breakfast" });
    expect(idempotencyKey).toBeTruthy();

    resolveCreate({ ...entry, grams: "110" });
    await waitFor(() => expect(onSaved).toHaveBeenCalledOnce());
  });

  it("keeps an edited entry open and refreshes it after a conflict", async () => {
    vi.mocked(api.updateRationEntry).mockRejectedValue(new api.APIError("Запись была изменена", 409));
    const onConflictRefresh = vi.fn().mockResolvedValue(undefined);

    renderFlow(
      <RationEntrySheet
        entry={entry}
        currentDate="2026-09-13"
        format="automatic"
        initData="test-init-data"
        authorized
        formatValue={(value) => String(value)}
        onClose={vi.fn()}
        onChanged={vi.fn()}
        onConflictRefresh={onConflictRefresh}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Изменить" }));
    fireEvent.change(screen.getByLabelText("Количество, г"), { target: { value: "125" } });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));

    expect(await screen.findByText("Запись уже изменилась")).toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: "Изменить запись" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Загрузить актуальную" }));
    await waitFor(() => expect(onConflictRefresh).toHaveBeenCalledWith(entry.id));
  });
});
