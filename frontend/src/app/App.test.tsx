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
    platform: "browser",
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
    ["/ration", "Баланс КБЖУ"],
    ["/food", "Ингредиенты"],
    ["/weight", "Текущий вес"],
    ["/profile", "Внешний вид"],
  ])("opens %s directly", async (path, heading) => {
    renderApp(path);
    expect(await screen.findByText(heading, {}, { timeout: 3_000 })).toBeInTheDocument();
  });

  it("uses the configured default section instead of stale local history", async () => {
    localStorage.setItem("miniapp:last-section", "weight");
    renderApp("/");
    expect(await screen.findByText("Баланс КБЖУ")).toBeInTheDocument();
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

  it("keeps the ration date and meal when the food editor is closed", async () => {
    renderApp("/food/new?kind=ingredients&return=ration&date=2026-09-10&meal=lunch");
    fireEvent.click(screen.getByRole("button", { name: "Закрыть" }));

    expect(await screen.findByRole("dialog", { name: "Добавить в рацион" })).toBeInTheDocument();
    expect(screen.getByText(/10 сентября · Обед/i)).toBeInTheDocument();
  });

  it("keeps macro grams and the four default meals visible without goals", () => {
    renderApp("/ration");

    expect(screen.getByText("Цели не заданы")).toBeInTheDocument();
    expect(screen.getAllByText("0 г")).toHaveLength(3);
    for (const meal of ["Завтрак", "Обед", "Ужин", "Перекус"]) {
      expect(screen.getByRole("heading", { name: meal })).toBeInTheDocument();
    }
    expect(screen.queryByRole("heading", { name: "Другое" })).not.toBeInTheDocument();
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

  it("offers button controls for the interactive weight window", async () => {
    renderApp("/weight");

    const next = await screen.findByRole("button", { name: "Следующий период" });
    const reset = screen.getByRole("button", { name: "Вернуться к текущему периоду" });
    expect(next).toBeDisabled();
    expect(reset).toBeDisabled();
    expect(screen.getAllByText("30 дней")).toHaveLength(2);

    fireEvent.click(screen.getByRole("button", { name: "Предыдущий период" }));
    expect(next).toBeEnabled();
    expect(reset).toBeEnabled();

    fireEvent.click(screen.getByRole("button", { name: "Приблизить график" }));
    expect(screen.getByText("20 дней")).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Период графика" })).toHaveValue("custom");

    fireEvent.click(reset);
    expect(screen.getByRole("button", { name: "Вернуться к текущему периоду" })).toBeDisabled();
  });

  it("rejects short chart windows and future weight measurements", async () => {
    renderApp("/weight");
    fireEvent.change(await screen.findByRole("combobox", { name: "Период графика" }), {
      target: { value: "custom" },
    });
    const [from, to] = screen.getAllByDisplayValue(/\d{4}-\d{2}-\d{2}/);
    fireEvent.change(from, { target: { value: "2026-09-10" } });
    fireEvent.change(to, { target: { value: "2026-09-14" } });
    expect(screen.getByText("Период не может быть короче 7 дней")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Записать" }));
    fireEvent.change(screen.getByLabelText("Дата и время"), { target: { value: "2099-01-01T12:00" } });
    expect(screen.getByText("Дата измерения не может быть в будущем")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Сохранить" })).toBeDisabled();
  });

  it("switches the preview theme from profile settings", () => {
    renderApp("/profile");
    fireEvent.click(screen.getByRole("button", { name: /ТемаСистемная/ }));
    fireEvent.click(screen.getByRole("button", { name: "Темная" }));
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(document.documentElement.dataset.themeMode).toBe("dark");
  });

  it("keeps profile forms collapsed until their setting is opened", () => {
    renderApp("/profile");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByText(/Фактические КБЖУ в рационе все равно отображаются/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Настроить" }));
    expect(screen.getByRole("dialog", { name: "Цели питания" })).toBeInTheDocument();
    expect(screen.getByLabelText("Белки, г")).toBeInTheDocument();
  });

  it("marks a future ration date explicitly", () => {
    renderApp("/ration");
    fireEvent.click(screen.getByRole("button", { name: "Следующий день" }));
    expect(screen.getByText("Будущая дата")).toBeInTheDocument();
    expect(screen.getByText("Будущий день")).toBeInTheDocument();
  });

  it.each(["/privacy", "/privacy-policy"])(
    "keeps the privacy policy publicly accessible at %s",
    (path) => {
      renderApp(path, createPreviewAdapter({ isDevelopmentPreview: false }));
      expect(
        screen.getByRole("heading", { name: "Политика конфиденциальности" }),
      ).toBeInTheDocument();
      expect(screen.queryByText("Откройте приложение из Telegram")).not.toBeInTheDocument();
    },
  );

  it("blocks the application outside Telegram in production", () => {
    renderApp(
      "/ration",
      createPreviewAdapter({ isDevelopmentPreview: false, isTelegram: false }),
    );

    expect(screen.getByText("Откройте приложение из Telegram")).toBeInTheDocument();
    expect(screen.queryByText("Баланс КБЖУ")).not.toBeInTheDocument();
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

  it("reserves Telegram header controls when the client reports no top inset", () => {
    renderApp("/ration", createPreviewAdapter({
      isTelegram: true,
      platform: "ios",
      viewport: {
        stableHeight: 568,
        safeArea: { top: 0, right: 0, bottom: 0, left: 0 },
        contentSafeArea: { top: 0, right: 0, bottom: 0, left: 0 },
      },
    }));

    expect(document.documentElement.style.getPropertyValue("--app-header-fallback")).toBe("72px");
    expect(document.documentElement.style.getPropertyValue("--app-header-safe-top-js")).toBe("72px");
    expect(document.querySelector(".app-shell")).toHaveClass("app-shell--telegram");
    expect(document.querySelector(".telegram-controls-spacer")).toBeInTheDocument();
    expect(screen.queryByText("WTracker")).not.toBeInTheDocument();
  });

  it("uses a larger Telegram content safe area instead of the platform fallback", () => {
    renderApp("/ration", createPreviewAdapter({
      isTelegram: true,
      platform: "ios",
      viewport: {
        stableHeight: 568,
        safeArea: { top: 59, right: 0, bottom: 21, left: 0 },
        contentSafeArea: { top: 96, right: 0, bottom: 0, left: 0 },
      },
    }));

    expect(document.documentElement.style.getPropertyValue("--app-header-fallback")).toBe("72px");
    expect(document.documentElement.style.getPropertyValue("--app-header-safe-top-js")).toBe("96px");
  });
});
