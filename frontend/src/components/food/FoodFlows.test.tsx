import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState, type ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as api from "../../api/client";
import { ToastProvider } from "../ui";
import { BarcodeScannerSheet } from "./BarcodeScannerSheet";
import { FoodEditorSheet } from "./FoodEditorSheet";

const scannerMock = vi.hoisted(() => ({ decodeFromConstraints: vi.fn() }));

vi.mock("@zxing/browser", () => ({
  BarcodeFormat: { EAN_8: 1, UPC_A: 2, EAN_13: 3, ITF: 4, CODE_128: 5 },
  BrowserMultiFormatReader: class {
    public possibleFormats: number[] = [];
    public decodeFromConstraints = scannerMock.decodeFromConstraints;
  },
}));

vi.mock("../../api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/client")>();
  return {
    ...actual,
    createDish: vi.fn(),
    createIngredient: vi.fn(),
    createBarcodeIngredient: vi.fn(),
    deleteFood: vi.fn(),
    fetchDeleteConsequence: vi.fn(),
    fetchIngredients: vi.fn(),
    lookupBarcode: vi.fn(),
  };
});

const firstIngredient: api.Ingredient = {
  id: "1",
  name: "Йогурт",
  nutrition_per_100g: { energy_kcal: "60", protein_g: "4", fat_g: "2", carbs_g: "6" },
  folder_id: null,
  package_weight_g: null,
  photo_url: null,
  source_name: null,
  source_url: null,
  created_at: "2026-09-14T00:00:00Z",
  updated_at: "2026-09-14T00:00:00Z",
};

const secondIngredient: api.Ingredient = {
  ...firstIngredient,
  id: "2",
  name: "Банан",
  nutrition_per_100g: { energy_kcal: "90", protein_g: "1", fat_g: "0.3", carbs_g: "23" },
};

function renderFlow(node: ReactNode) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>{node}</ToastProvider>
    </QueryClientProvider>,
  );
}

function editorProps() {
  return {
    open: true,
    item: null,
    initData: "test-init-data",
    authorized: true,
    folders: [],
    onClose: vi.fn(),
    onOpenExisting: vi.fn(),
  };
}

describe("food editor flows", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.fetchIngredients).mockResolvedValue({ items: [firstIngredient], next_cursor: null });
  });

  it("asks before discarding an edited ingredient", () => {
    const props = editorProps();
    renderFlow(<FoodEditorSheet {...props} kind="ingredients" />);

    fireEvent.change(screen.getByLabelText("Название"), { target: { value: "Новый продукт" } });
    fireEvent.click(screen.getByRole("button", { name: "Закрыть" }));

    expect(screen.getByRole("alertdialog", { name: "Отменить изменения?" })).toBeInTheDocument();
    expect(props.onClose).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Выйти без сохранения" }));
    expect(props.onClose).toHaveBeenCalledOnce();
  });

  it("shows a server validation message next to its field", async () => {
    vi.mocked(api.createIngredient).mockRejectedValue(
      new api.APIError("Проверьте поля", 422, undefined, undefined, { "body.name": "Название слишком короткое" }),
    );
    renderFlow(<FoodEditorSheet {...editorProps()} kind="ingredients" />);

    fireEvent.change(screen.getByLabelText("Название"), { target: { value: "А" } });
    fireEvent.change(screen.getByLabelText("Ккал"), { target: { value: "1" } });
    fireEvent.change(screen.getByLabelText("Белки, г"), { target: { value: "1" } });
    fireEvent.change(screen.getByLabelText("Жиры, г"), { target: { value: "1" } });
    fireEvent.change(screen.getByLabelText("Углеводы, г"), { target: { value: "1" } });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить" }));

    expect(await screen.findByText("Название слишком короткое")).toBeInTheDocument();
    expect(screen.getByLabelText("Название")).toHaveAttribute("aria-invalid", "true");
  });

  it("loads the next ingredient page instead of silently limiting dish search", async () => {
    vi.mocked(api.fetchIngredients).mockImplementation(async (_initData, _query, _sort, cursor) =>
      cursor
        ? { items: [secondIngredient], next_cursor: null }
        : { items: [firstIngredient], next_cursor: "next-page" },
    );
    renderFlow(<FoodEditorSheet {...editorProps()} kind="dishes" />);

    fireEvent.click(await screen.findByRole("button", { name: /Йогурт/ }));
    fireEvent.change(screen.getByLabelText("Название"), { target: { value: "Завтрак" } });
    fireEvent.click(screen.getByRole("button", { name: "Показать ещё" }));

    expect(await screen.findByRole("button", { name: /Банан/ })).toBeInTheDocument();
    expect(api.fetchIngredients).toHaveBeenCalledWith("test-init-data", "", "name_asc", "next-page");
    expect(screen.getByLabelText("Итоги блюда")).toHaveTextContent("60");
    expect(screen.getByRole("button", { name: "Сохранить" })).toBeEnabled();
  });

  it("checks consequences and deletes without a dialog when confirmations are disabled", async () => {
    vi.mocked(api.fetchDeleteConsequence).mockResolvedValue({ can_delete: true, message: "Можно удалить", dependencies: [] });
    vi.mocked(api.deleteFood).mockResolvedValue(undefined);
    const props = { ...editorProps(), item: firstIngredient, confirmDeletions: false };
    renderFlow(<FoodEditorSheet {...props} kind="ingredients" />);

    fireEvent.click(screen.getByRole("button", { name: "Удалить" }));

    await waitFor(() => expect(api.fetchDeleteConsequence).toHaveBeenCalled());
    await waitFor(() => expect(api.deleteFood).toHaveBeenCalledWith("test-init-data", "ingredients", firstIngredient.id));
    expect(screen.queryByRole("alertdialog", { name: "Удалить безвозвратно?" })).not.toBeInTheDocument();
    expect(props.onClose).toHaveBeenCalledOnce();
  });
});

describe("barcode flow", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    scannerMock.decodeFromConstraints.mockReset();
  });

  it("keeps a not-found barcode separate from manual product confirmation", async () => {
    vi.mocked(api.lookupBarcode).mockResolvedValue({
      barcode: "12345670",
      found: false,
      name: null,
      brand: null,
      package_weight_g: null,
      package_quantity: null,
      package_quantity_unit: null,
      serving_size: null,
      nutrition_per_100g: { energy_kcal: null, protein_g: null, fat_g: null, carbs_g: null },
      photo_url: null,
      missing_fields: ["name", "energy_kcal", "protein_g", "fat_g", "carbs_g"],
      derived_fields: [],
      source: "open_food_facts",
      source_url: "https://world.openfoodfacts.org/product/12345670",
      confirmation_token: "test-confirmation-token",
    });
    renderFlow(<BarcodeScannerSheet open initData="test-init-data" folders={[]} onClose={vi.fn()} onOpenExisting={vi.fn()} />);

    fireEvent.change(screen.getByLabelText("Штрихкод"), { target: { value: "12345670" } });
    fireEvent.click(screen.getByRole("button", { name: "Найти продукт" }));

    expect(await screen.findByRole("heading", { name: "В Open Food Facts продукт не найден" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Название")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Заполнить вручную" }));
    expect(screen.getByLabelText("Название")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Создать ингредиент" })).toBeDisabled();
    expect(screen.getByText(/Я проверил название/)).toBeInTheDocument();
    await waitFor(() => expect(api.lookupBarcode).toHaveBeenCalledWith("test-init-data", "12345670"));
  });

  it("stops scanner controls that resolve after the sheet was closed", async () => {
    let resolveScanner: (controls: { stop: () => void }) => void = () => undefined;
    const controls = { stop: vi.fn() };
    scannerMock.decodeFromConstraints.mockReturnValue(new Promise((resolve) => { resolveScanner = resolve; }));
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia: vi.fn() },
    });
    function Harness() {
      const [open, setOpen] = useState(true);
      return <BarcodeScannerSheet open={open} initData="test-init-data" folders={[]} onClose={() => setOpen(false)} onOpenExisting={vi.fn()} />;
    }
    renderFlow(<Harness />);

    fireEvent.click(screen.getByRole("button", { name: "Включить камеру" }));
    await waitFor(() => expect(scannerMock.decodeFromConstraints).toHaveBeenCalledOnce());
    fireEvent.click(screen.getByRole("button", { name: "Закрыть" }));
    resolveScanner(controls);

    await waitFor(() => expect(controls.stop).toHaveBeenCalledOnce());
    expect(screen.queryByRole("dialog", { name: "Добавить по штрихкоду" })).not.toBeInTheDocument();
  });
});
