import { useEffect, useRef } from "react";
import { Outlet, useLocation } from "react-router-dom";

import type { MiniAppContext } from "../../app/context";
import type { DefaultSection } from "../../api/client";
import type { TelegramAdapter } from "../../telegram/adapter";
import { useTelegramBackButton } from "../../telegram/hooks";
import { BottomNavigation } from "./BottomNavigation";

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
  const contentRef = useRef<HTMLElement>(null);
  const rootPath = `/${location.pathname.split("/").filter(Boolean)[0] ?? ""}`;
  useTelegramBackButton(telegram);

  useEffect(() => {
    const section = SECTION_BY_PATH[rootPath];
    if (section) localStorage.setItem("miniapp:last-section", section);
  }, [rootPath]);

  useEffect(() => {
    const content = contentRef.current;
    if (!content) return;
    if (typeof content.scrollTo === "function") content.scrollTo({ top: 0 });
    else content.scrollTop = 0;
  }, [rootPath]);

  return (
    <div className={`app-shell ${telegram.isTelegram ? "app-shell--telegram" : ""} ${context.preferences.compact_lists ? "is-compact" : ""}`}>
      {telegram.isTelegram && <div className="telegram-controls-spacer" aria-hidden="true" />}
      <main ref={contentRef} className="app-content" id="main-content" tabIndex={-1}>
        <Outlet context={context} />
      </main>
      <BottomNavigation />
    </div>
  );
}
