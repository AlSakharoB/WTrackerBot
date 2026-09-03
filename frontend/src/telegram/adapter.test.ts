import { afterEach, describe, expect, it, vi } from "vitest";

import { createTelegramAdapter } from "./adapter";

describe("createTelegramAdapter", () => {
  afterEach(() => {
    delete window.Telegram;
  });

  it("uses signed initData and initializes Telegram WebApp", () => {
    const ready = vi.fn();
    const expand = vi.fn();
    const onEvent = vi.fn();
    const offEvent = vi.fn();
    window.Telegram = {
      WebApp: {
        initData: "signed-data",
        colorScheme: "dark",
        ready,
        expand,
        onEvent,
        offEvent,
      },
    };

    const adapter = createTelegramAdapter();
    adapter.initialize();

    expect(adapter.initData).toBe("signed-data");
    expect(adapter.colorScheme).toBe("dark");
    expect(adapter.isTelegram).toBe(true);
    expect(ready).toHaveBeenCalledOnce();
    expect(expand).toHaveBeenCalledOnce();
  });

  it("binds viewport events and Telegram BackButton", () => {
    const onEvent = vi.fn();
    const offEvent = vi.fn();
    const show = vi.fn();
    const hide = vi.fn();
    const onClick = vi.fn();
    const offClick = vi.fn();
    window.Telegram = {
      WebApp: {
        initData: "signed-data",
        colorScheme: "light",
        viewportStableHeight: 720,
        safeAreaInset: { top: 10, right: 1, bottom: 20, left: 1 },
        BackButton: { show, hide, onClick, offClick },
        ready: vi.fn(),
        expand: vi.fn(),
        onEvent,
        offEvent,
      },
    };
    const adapter = createTelegramAdapter();
    const viewportCleanup = adapter.subscribeViewport(vi.fn());
    const backCallback = vi.fn();
    const backCleanup = adapter.bindBackButton(backCallback);

    expect(adapter.viewport.stableHeight).toBe(720);
    expect(adapter.viewport.safeArea.bottom).toBe(20);
    expect(onEvent).toHaveBeenCalledTimes(3);
    expect(onClick).toHaveBeenCalledWith(backCallback);
    expect(show).toHaveBeenCalledOnce();

    viewportCleanup();
    backCleanup();
    expect(offEvent).toHaveBeenCalledTimes(3);
    expect(offClick).toHaveBeenCalledWith(backCallback);
    expect(hide).toHaveBeenCalledOnce();
  });

  it("does not invent authorization outside Telegram", () => {
    const adapter = createTelegramAdapter();

    expect(adapter.isTelegram).toBe(false);
    expect(adapter.initData).toBe("");
  });

  it("uses preview mode when Telegram script has no launch data in development", () => {
    window.Telegram = {
      WebApp: {
        initData: "",
        colorScheme: "light",
        ready: vi.fn(),
        expand: vi.fn(),
        onEvent: vi.fn(),
        offEvent: vi.fn(),
      },
    };

    const adapter = createTelegramAdapter();

    expect(adapter.isTelegram).toBe(false);
    expect(adapter.isDevelopmentPreview).toBe(true);
  });
});
