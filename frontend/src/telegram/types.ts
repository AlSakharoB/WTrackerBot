export interface TelegramInset {
  top: number;
  right: number;
  bottom: number;
  left: number;
}

export interface TelegramBackButton {
  show(): void;
  hide(): void;
  onClick(callback: () => void): void;
  offClick(callback: () => void): void;
}

export type TelegramEvent =
  | "themeChanged"
  | "viewportChanged"
  | "safeAreaChanged"
  | "contentSafeAreaChanged"
  | "fullscreenChanged";

export interface TelegramWebApp {
  readonly initData: string;
  readonly version?: string;
  readonly platform?: string;
  readonly colorScheme: "light" | "dark";
  readonly isFullscreen?: boolean;
  readonly viewportStableHeight?: number;
  readonly safeAreaInset?: TelegramInset;
  readonly contentSafeAreaInset?: TelegramInset;
  readonly BackButton?: TelegramBackButton;
  ready(): void;
  expand(): void;
  isVersionAtLeast?(version: string): boolean;
  requestFullscreen?(): void;
  close?(): void;
  onEvent(event: TelegramEvent, callback: () => void): void;
  offEvent(event: TelegramEvent, callback: () => void): void;
}

declare global {
  interface Window {
    Telegram?: { WebApp?: TelegramWebApp };
  }
}
