import type { TelegramInset, TelegramWebApp } from "./types";

export interface TelegramViewport {
  stableHeight: number | null;
  safeArea: TelegramInset;
  contentSafeArea: TelegramInset;
}

const EMPTY_INSET: TelegramInset = { top: 0, right: 0, bottom: 0, left: 0 };

export interface TelegramAdapter {
  readonly initData: string;
  readonly colorScheme: "light" | "dark";
  readonly isTelegram: boolean;
  readonly isDevelopmentPreview: boolean;
  readonly viewport: TelegramViewport;
  initialize(): void;
  subscribeTheme(callback: () => void): () => void;
  subscribeViewport(callback: () => void): () => void;
  bindBackButton(callback: () => void): () => void;
  close?(): void;
}

class WebAppTelegramAdapter implements TelegramAdapter {
  public readonly isTelegram = true;
  public readonly isDevelopmentPreview = false;

  public constructor(private readonly webApp: TelegramWebApp) {}

  public get initData(): string {
    return this.webApp.initData;
  }

  public get colorScheme(): "light" | "dark" {
    return this.webApp.colorScheme;
  }

  public get viewport(): TelegramViewport {
    return {
      stableHeight: this.webApp.viewportStableHeight ?? null,
      safeArea: this.webApp.safeAreaInset ?? EMPTY_INSET,
      contentSafeArea: this.webApp.contentSafeAreaInset ?? EMPTY_INSET,
    };
  }

  public initialize(): void {
    this.webApp.ready();
    this.webApp.expand();
  }

  public subscribeTheme(callback: () => void): () => void {
    this.webApp.onEvent("themeChanged", callback);
    return () => this.webApp.offEvent("themeChanged", callback);
  }

  public subscribeViewport(callback: () => void): () => void {
    const events = [
      "viewportChanged",
      "safeAreaChanged",
      "contentSafeAreaChanged",
    ] as const;
    for (const event of events) this.webApp.onEvent(event, callback);
    return () => {
      for (const event of events) this.webApp.offEvent(event, callback);
    };
  }

  public bindBackButton(callback: () => void): () => void {
    const backButton = this.webApp.BackButton;
    if (!backButton) return () => undefined;
    backButton.onClick(callback);
    backButton.show();
    return () => {
      backButton.offClick(callback);
      backButton.hide();
    };
  }

  public close(): void {
    this.webApp.close?.();
  }
}

class BrowserDevelopmentAdapter implements TelegramAdapter {
  public readonly isTelegram = false;
  public readonly isDevelopmentPreview = import.meta.env.DEV;

  public get colorScheme(): "light" | "dark" {
    return window.matchMedia?.("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  }

  public get viewport(): TelegramViewport {
    return {
      stableHeight: window.visualViewport?.height ?? window.innerHeight,
      safeArea: EMPTY_INSET,
      contentSafeArea: EMPTY_INSET,
    };
  }

  public get initData(): string {
    return import.meta.env.DEV ? (import.meta.env.VITE_DEV_INIT_DATA ?? "") : "";
  }

  public initialize(): void {}

  public subscribeTheme(callback: () => void): () => void {
    const mediaQuery = window.matchMedia?.("(prefers-color-scheme: dark)");
    mediaQuery?.addEventListener("change", callback);
    return () => mediaQuery?.removeEventListener("change", callback);
  }

  public subscribeViewport(callback: () => void): () => void {
    window.visualViewport?.addEventListener("resize", callback);
    window.addEventListener("resize", callback);
    return () => {
      window.visualViewport?.removeEventListener("resize", callback);
      window.removeEventListener("resize", callback);
    };
  }

  public bindBackButton(): () => void {
    return () => undefined;
  }
}

export function createTelegramAdapter(): TelegramAdapter {
  const webApp = window.Telegram?.WebApp;
  return webApp && (webApp.initData.length > 0 || !import.meta.env.DEV)
    ? new WebAppTelegramAdapter(webApp)
    : new BrowserDevelopmentAdapter();
}
