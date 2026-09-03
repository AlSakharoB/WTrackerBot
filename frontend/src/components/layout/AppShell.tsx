import { useEffect } from "react";
import { Outlet, useLocation } from "react-router-dom";

import type { MiniAppContext } from "../../app/context";
import type { DefaultSection } from "../../api/client";
import type { TelegramAdapter } from "../../telegram/adapter";
import { useTelegramBackButton } from "../../telegram/hooks";
import { BottomNavigation } from "./BottomNavigation";
import { TopBar } from "./TopBar";

const SECTION_META: Record<string, { title: string; subtitle?: string }> = {
  "/ration": { title: "Рацион", subtitle: "Дневник питания" },
  "/food": { title: "Еда", subtitle: "Ингредиенты и блюда" },
  "/weight": { title: "Вес", subtitle: "Динамика и цель" },
  "/profile": { title: "Профиль", subtitle: "Настройки" },
};

const SECTION_BY_PATH: Record<string, DefaultSection> = {
  "/ration": "ration",
  "/food": "food",
  "/weight": "weight",
  "/profile": "profile",
};

interface AppShellProps {
  telegram: TelegramAdapter;
  context: MiniAppContext;
}

export function AppShell({ telegram, context }: AppShellProps) {
  const location = useLocation();
  const rootPath = `/${location.pathname.split("/").filter(Boolean)[0] ?? ""}`;
  const meta = SECTION_META[rootPath] ?? { title: "WTrackerBot" };
  useTelegramBackButton(telegram);

  useEffect(() => {
    const section = SECTION_BY_PATH[rootPath];
    if (section) localStorage.setItem("miniapp:last-section", section);
  }, [rootPath]);

  return (
    <div className={`app-shell ${context.preferences.compact_lists ? "is-compact" : ""}`}>
      <TopBar title={meta.title} subtitle={meta.subtitle} />
      <main className="app-content" id="main-content">
        <Outlet context={context} />
      </main>
      <BottomNavigation />
    </div>
  );
}
