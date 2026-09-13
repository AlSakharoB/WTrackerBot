import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { TelegramAdapter } from "../telegram/adapter";
import { stopVideoTracks } from "../components/food/camera";
import { App } from "./App";

function createPreviewAdapter(overrides: Partial<TelegramAdapter> = {}): TelegramAdapter {
  return {
    initData: "",
    colorScheme: "light",
    isTelegram: false,
    isDevelopmentPreview: true,
    viewport: {
      stableHeight: 800,
      safeArea: { top: 0, right: 0, bottom: 0, left: 0 },
      contentSafeArea: { top: 0, right: 0, bottom: 0, left: 0 },
    },
    initialize: vi.fn(),
    subscribeTheme: vi.fn(() => () => undefined),
    subscribeViewport: vi.fn(() => () => undefined),
    bindBackButton: vi.fn(() => () => undefined),
    ...overrides,
  };
}

function renderApp(path: string, telegram = createPreviewAdapter()) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={queryClient}>
        <App telegram={telegram} />
      </QueryClientProvider>
    </MemoryRouter>,
  );
  return telegram;
}

describe("Mini App routes", () => {
  beforeEach(() => localStorage.clear());
  afterEach(() => {
    document.documentElement.removeAttribute("data-theme");
    document.documentElement.removeAttribute("data-theme-mode");
    document.documentElement.removeAttribute("style");
  });

  it.each([
    ["/ration", "Итоги дня"],
    ["/food", "Ингредиенты"],
    ["/weight", "Текущий вес"],
    ["/profile", "Внешний вид"],
  ])("opens %s directly", async (path, heading) => {
    renderApp(path);
    expect(await screen.findByText(heading)).toBeInTheDocument();
  });

  it("restores the last primary section from local storage", async () => {
    localStorage.setItem("miniapp:last-section", "weight");
    renderApp("/");
    expect(await screen.findByText("Текущий вес")).toBeInTheDocument();
  });

  it("moves through bottom navigation and stores the selected section", () => {
    renderApp("/ration");
    fireEvent.click(screen.getByRole("link", { name: "Еда" }));
    expect(screen.getByPlaceholderText("Найти ингредиент")).toBeInTheDocument();
    expect(localStorage.getItem("miniapp:last-section")).toBe("food");
  });

  it("binds Telegram BackButton for nested or unknown routes", () => {
    const telegram = createPreviewAdapter();
    renderApp("/food/new", telegram);
    expect(screen.getByRole("dialog", { name: "Добавить ингредиент" })).toBeInTheDocument();
    expect(telegram.bindBackButton).toHaveBeenCalledOnce();
  });

  it("uses Telegram BackButton to close an overlay on a primary route", async () => {
    let handleBack: () => void = () => undefined;
    const bindBackButton = vi.fn((callback: () => void) => {
      handleBack = callback;
      return () => undefined;
    });
    const telegram = createPreviewAdapter({ bindBackButton });
    renderApp("/weight", telegram);

    fireEvent.click(await screen.findByRole("button", { name: "Записать" }));
    expect(screen.getByRole("dialog", { name: "Записать вес" })).toBeInTheDocument();
    await waitFor(() => expect(bindBackButton).toHaveBeenCalledOnce());

    handleBack();
    await waitFor(() => {
      expect(screen.queryByRole("dialog", { name: "Записать вес" })).not.toBeInTheDocument();
    });
  });

  it("opens the searchable dish editor from a direct route", () => {
    renderApp("/food/new?kind=dishes");
    expect(screen.getByRole("dialog", { name: "Добавить блюдо" })).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Добавить ингредиент")).toBeInTheDocument();
    expect(screen.getByLabelText("Итоги блюда")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Сохранить" })).toBeDisabled();
  });

  it("opens food folder management without leaving the catalog", () => {
    renderApp("/food");
    fireEvent.click(screen.getByRole("button", { name: "Управлять папками" }));
    expect(screen.getByRole("dialog", { name: "Папки еды" })).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Новая папка")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Создать папку" })).toBeDisabled();
  });

  it("offers manual barcode entry when the camera is unavailable", () => {
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: undefined,
    });
    renderApp("/food");
    fireEvent.click(screen.getByRole("button", { name: "Сканировать штрихкод" }));
    expect(screen.getByRole("dialog", { name: "Добавить по штрихкоду" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Включить камеру" }));
    expect(screen.getByText(/Камера недоступна/)).toBeInTheDocument();
    expect(screen.getByLabelText("Штрихкод")).toBeInTheDocument();
  });

  it("stops every camera track", () => {
    const first = { stop: vi.fn() };
    const second = { stop: vi.fn() };
    const video = document.createElement("video");
    Object.defineProperty(video, "srcObject", {
      configurable: true,
      writable: true,
      value: { getTracks: () => [first, second] },
    });

    stopVideoTracks(video);

    expect(first.stop).toHaveBeenCalledOnce();
    expect(second.stop).toHaveBeenCalledOnce();
    expect(video.srcObject).toBeNull();
  });

  it("opens the ration source picker as a nested route", () => {
    const telegram = createPreviewAdapter();
    renderApp("/ration/add?date=2026-09-10&meal=breakfast", telegram);

    expect(screen.getByRole("dialog", { name: "Добавить в рацион" })).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Найти ингредиент или блюдо")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ингредиенты" })).toBeInTheDocument();
    expect(telegram.bindBackButton).toHaveBeenCalledOnce();
  });

  it("opens the weight entry and goal forms", async () => {
    renderApp("/weight");

    fireEvent.click(await screen.findByRole("button", { name: "Записать" }));
    expect(screen.getByRole("dialog", { name: "Записать вес" })).toBeInTheDocument();
    expect(screen.getByLabelText("Вес, кг")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Закрыть" }));

    fireEvent.click(screen.getByRole("button", { name: "Задать" }));
    expect(screen.getByRole("dialog", { name: "Задать цель" })).toBeInTheDocument();
    expect(screen.getByLabelText("Целевой вес, кг")).toBeInTheDocument();
  });

  it("validates a custom weight range of no more than one year", async () => {
    renderApp("/weight");
    fireEvent.change(await screen.findByRole("combobox", { name: "Период графика" }), {
      target: { value: "custom" },
    });
    const [from, to] = screen.getAllByDisplayValue(/\d{4}-\d{2}-\d{2}/);
    fireEvent.change(from, { target: { value: "2025-01-01" } });
    fireEvent.change(to, { target: { value: "2026-09-10" } });
    expect(screen.getByText("Период не может быть больше 365 дней")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Показать" })).toBeDisabled();
  });

  it("switches the preview theme from profile settings", () => {
    renderApp("/profile");
    fireEvent.click(screen.getByRole("button", { name: "Темная" }));
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(document.documentElement.dataset.themeMode).toBe("dark");
  });

  it("marks a future ration date explicitly", () => {
    renderApp("/ration");
    fireEvent.click(screen.getByRole("button", { name: "Следующий день" }));
    expect(screen.getByText("Будущая дата")).toBeInTheDocument();
    expect(screen.getByText("Будущий день")).toBeInTheDocument();
  });

  it("keeps the privacy policy publicly accessible", () => {
    renderApp(
      "/privacy-policy",
      createPreviewAdapter({ isDevelopmentPreview: false }),
    );
    expect(screen.getByRole("heading", { name: "Политика конфиденциальности" })).toBeInTheDocument();
    expect(screen.queryByText("Откройте приложение из Telegram")).not.toBeInTheDocument();
  });

  it("applies stable viewport and safe area values", () => {
    renderApp("/ration", createPreviewAdapter({
      viewport: {
        stableHeight: 568,
        safeArea: { top: 12, right: 0, bottom: 18, left: 0 },
        contentSafeArea: { top: 4, right: 0, bottom: 8, left: 0 },
      },
    }));
    expect(document.documentElement.style.getPropertyValue("--app-stable-height")).toBe("568px");
    expect(document.documentElement.style.getPropertyValue("--app-safe-bottom")).toBe("18px");
  });
});
