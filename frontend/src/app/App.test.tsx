import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { TelegramAdapter } from "../telegram/adapter";
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
    document.documentElement.removeAttribute("style");
  });

  it.each([
    ["/ration", "Итоги дня"],
    ["/food", "Ингредиенты"],
    ["/weight", "Текущий вес"],
    ["/profile", "Внешний вид"],
  ])("opens %s directly", (path, heading) => {
    renderApp(path);
    expect(screen.getByText(heading)).toBeInTheDocument();
  });

  it("restores the last primary section from local storage", () => {
    localStorage.setItem("miniapp:last-section", "weight");
    renderApp("/");
    expect(screen.getByText("Текущий вес")).toBeInTheDocument();
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
    expect(screen.getByRole("dialog", { name: "Добавить еду" })).toBeInTheDocument();
    expect(telegram.bindBackButton).toHaveBeenCalledOnce();
  });

  it("opens the ration source picker as a nested route", () => {
    const telegram = createPreviewAdapter();
    renderApp("/ration/add?date=2026-09-10&meal=breakfast", telegram);

    expect(screen.getByRole("dialog", { name: "Добавить в рацион" })).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Найти ингредиент или блюдо")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Ингредиенты" })).toBeInTheDocument();
    expect(telegram.bindBackButton).toHaveBeenCalledOnce();
  });

  it("switches the preview theme from profile settings", () => {
    renderApp("/profile");
    fireEvent.click(screen.getByRole("button", { name: "Темная" }));
    expect(document.documentElement.dataset.theme).toBe("dark");
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
