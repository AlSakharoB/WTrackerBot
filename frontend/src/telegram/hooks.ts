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

function setViewportVariables(telegram: TelegramAdapter) {
  const { stableHeight, safeArea, contentSafeArea } = telegram.viewport;
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
}

export function useTelegramEnvironment(
  telegram: TelegramAdapter,
  themeMode: ThemeMode,
) {
  useEffect(() => {
    const applyTheme = () => {
      document.documentElement.dataset.themeMode = themeMode;
      document.documentElement.dataset.theme =
        themeMode === "system" ? telegram.colorScheme : themeMode;
    };
    applyTheme();
    return telegram.subscribeTheme(applyTheme);
  }, [telegram, themeMode]);

  useEffect(() => {
    const applyViewport = () => setViewportVariables(telegram);
    applyViewport();
    return telegram.subscribeViewport(applyViewport);
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
