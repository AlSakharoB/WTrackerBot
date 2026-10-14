import { useEffect, useSyncExternalStore } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import type { ThemeMode } from "../api/client";
import {
  closeTopModalLayer,
  hasOpenModalLayer,
  subscribeModalLayers,
} from "../components/ui/modal-stack";
import type { TelegramAdapter } from "./adapter";

const PRIMARY_ROUTES = new Set(["/ration", "/food", "/weight", "/profile"]);
const TELEGRAM_HEADER_GAP = 8;

function cssColorToHex(color: string): string | null {
  const values = color.match(/\d+(?:\.\d+)?/g)?.map(Number);
  if (!values || values.length < 3 || (values.length >= 4 && values[3] === 0)) {
    return null;
  }
  const channels = values.slice(0, 3);
  return `#${channels
    .map((channel) => Math.max(0, Math.min(255, Math.round(channel)))
      .toString(16)
      .padStart(2, "0"))
    .join("")}`;
}

interface TelegramHeaderMetrics {
  controlsHeight: number;
  minimumHeight: number;
}

function telegramHeaderMetrics(platform: string): TelegramHeaderMetrics {
  switch (platform.toLowerCase()) {
    case "ios":
      return { controlsHeight: 44, minimumHeight: 104 };
    case "android":
    case "android_x":
      return { controlsHeight: 48, minimumHeight: 80 };
    default:
      return { controlsHeight: 44, minimumHeight: 72 };
  }
}

function setViewportVariables(telegram: TelegramAdapter) {
  const { stableHeight, safeArea, contentSafeArea } = telegram.viewport;
  const metrics = telegramHeaderMetrics(telegram.platform);
  const headerFallback = telegram.isTelegram ? metrics.minimumHeight : 0;
  const telegramControlsBoundary = telegram.isTelegram
    ? safeArea.top + metrics.controlsHeight
    : safeArea.top;
  const headerInset = telegram.isTelegram
    ? Math.max(
        contentSafeArea.top,
        telegramControlsBoundary,
        headerFallback - TELEGRAM_HEADER_GAP,
      ) + TELEGRAM_HEADER_GAP
    : Math.max(safeArea.top, contentSafeArea.top);
  const root = document.documentElement.style;
  if (stableHeight !== null) {
    root.setProperty("--app-stable-height", `${stableHeight}px`);
  }
  root.setProperty("--app-safe-top", `${safeArea.top}px`);
  root.setProperty("--app-safe-right", `${safeArea.right}px`);
  root.setProperty("--app-safe-bottom", `${safeArea.bottom}px`);
  root.setProperty("--app-safe-left", `${safeArea.left}px`);
  root.setProperty("--app-content-safe-top", `${contentSafeArea.top}px`);
  root.setProperty("--app-content-safe-bottom", `${contentSafeArea.bottom}px`);
  root.setProperty("--app-header-fallback", `${headerFallback}px`);
  root.setProperty("--app-header-safe-top-js", `${headerInset}px`);
}

export function useTelegramEnvironment(
  telegram: TelegramAdapter,
  themeMode: ThemeMode,
) {
  useEffect(() => {
    const applyTheme = () => {
      const effectiveTheme = themeMode === "system" ? telegram.colorScheme : themeMode;
      document.documentElement.dataset.themeMode = themeMode;
      document.documentElement.dataset.theme = effectiveTheme;
      const computedBackground = window.getComputedStyle(document.body).backgroundColor;
      telegram.setChromeColor(
        cssColorToHex(computedBackground)
          ?? (effectiveTheme === "dark" ? "#111814" : "#f7f9f8"),
      );
    };
    applyTheme();
    return telegram.subscribeTheme(applyTheme);
  }, [telegram, themeMode]);

  useEffect(() => {
    const applyViewport = () => setViewportVariables(telegram);
    applyViewport();
    const unsubscribe = telegram.subscribeViewport(applyViewport);
    const frame = window.requestAnimationFrame?.(applyViewport);
    const timer = window.setTimeout(applyViewport, 250);
    return () => {
      unsubscribe();
      if (frame !== undefined) window.cancelAnimationFrame?.(frame);
      window.clearTimeout(timer);
    };
  }, [telegram]);
}

export function useTelegramBackButton(telegram: TelegramAdapter) {
  const location = useLocation();
  const navigate = useNavigate();
  const modalOpen = useSyncExternalStore(
    subscribeModalLayers,
    hasOpenModalLayer,
    () => false,
  );
  const visible = modalOpen || !PRIMARY_ROUTES.has(location.pathname);

  useEffect(() => {
    if (!visible) return;
    const routeRoot = `/${location.pathname.split("/").filter(Boolean)[0] ?? ""}`;
    const parentPath = PRIMARY_ROUTES.has(routeRoot) ? routeRoot : "/ration";
    return telegram.bindBackButton(() => {
      if (closeTopModalLayer()) return;
      navigate(parentPath, { replace: true });
    });
  }, [location.pathname, navigate, telegram, visible]);
}
