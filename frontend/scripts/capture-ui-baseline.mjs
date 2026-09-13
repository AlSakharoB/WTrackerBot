import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

import { createFixtures, ingredients, mutationResponse, NOW, TODAY } from "./ui-baseline-fixtures.mjs";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const base = new URL(process.env.UI_AUDIT_URL ?? "http://127.0.0.1:5173");
assert(["localhost", "127.0.0.1", "[::1]"].includes(base.hostname), "Only a local frontend is allowed");
assert.equal(base.protocol, "http:");
const output = resolve(root, process.env.UI_AUDIT_OUTPUT ?? "docs/miniapp-redesign/screenshots/baseline");
const viewports = [{ width: 320, height: 568 }, { width: 390, height: 844 }, { width: 768, height: 1024 }, { width: 1280, height: 800 }];
const ready = { ration: ".ration-summary", food: ".food-row", weight: ".weight-chart-dot", profile: ".profile-summary" };
const captures = [];
const diagnostics = [];
const errors = [];
const auditTitle = process.env.UI_AUDIT_TITLE ?? "MR1: текущий интерфейс";
await mkdir(output, { recursive: true });
await writeFile(resolve(output, "run-status.json"), '{"status":"running"}\n');
let browser;

async function openPage(section, { theme = "light", state = "populated", viewport = viewports[1], path = `/${section}`, telegramColors = false, safeArea = false } = {}) {
  const context = await browser.newContext({ viewport, deviceScaleFactor: 1, colorScheme: theme, locale: "ru-RU", timezoneId: "Europe/Moscow", reducedMotion: "reduce", serviceWorkers: "block", hasTouch: viewport.width < 768 });
  const page = await context.newPage();
  page.setDefaultTimeout(15000);
  page.on("pageerror", (error) => errors.push(`${section}/${state}: ${error.message}`));
  const fixtures = createFixtures(theme, state);
  const requests = [];
  const pendingRoutes = [];
  await context.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    // Even unknown API calls and external images must never reach a real service.
    if (url.origin !== base.origin) return route.fulfill({ status: 200, contentType: "application/javascript", body: "" });
    if (url.pathname.startsWith("/internal")) return route.abort();
    if (!url.pathname.startsWith("/api/")) return route.continue();
    const apiPath = url.pathname.replace(/^\/api\/v1/, "");
    requests.push(`${request.method()} ${url.pathname}${url.search}`);
    const respond = (json, status = 200) => route.fulfill({ status, json });
    if (state === "auth-error" && apiPath === "/me") return respond({ error: { message: "Срок авторизации истёк (тестовый ответ)" } }, 401);
    const primary = apiPath === ({ food: "/ingredients", profile: "/profile", weight: "/weight" }[section]) || (section === "ration" && /^\/ration\/\d/.test(apiPath));
    if (primary && state === "loading") { pendingRoutes.push(route); return; }
    if (primary && state === "error") return respond({ error: { message: "Сервис временно недоступен (тестовый ответ)", correlation_id: "audit-error" } }, 503);
    if (request.method() !== "GET") {
      if (apiPath === "/ingredients" && state === "duplicate") return respond({ error: { message: "Такой продукт уже существует", details: { existing: ingredients[0] } } }, 409);
      const result = mutationResponse(apiPath, state);
      if (result !== undefined) return respond(result);
    } else {
      if (/^\/ration\/\d{4}-\d{2}-\d{2}$/.test(apiPath)) {
        const date = apiPath.split("/").at(-1);
        return respond({ ...fixtures["/ration/day"], date, is_today: date === TODAY, is_future: date > TODAY });
      }
      if (apiPath.endsWith("/delete-consequences")) return respond({ can_delete: false, message: "Ингредиент используется в блюде. Сначала измените состав блюда.", dependencies: ["Овсянка с йогуртом и бананом"] });
      if (Object.hasOwn(fixtures, apiPath)) {
        const data = structuredClone(fixtures[apiPath]);
        if (data?.items && url.searchParams.has("q")) data.items = data.items.filter((item) => item.name.toLocaleLowerCase("ru-RU").includes(url.searchParams.get("q").toLocaleLowerCase("ru-RU")));
        return respond(data);
      }
    }
    errors.push(`Unmocked API: ${request.method()} ${apiPath}`);
    return respond({ error: { message: "Unmocked audit API" } }, 501);
  });
  await page.clock.setFixedTime(new Date(NOW));
  await page.addInitScript(({ theme, height, telegramColors, safeArea, state }) => {
    const noop = () => {};
    window.Telegram = { WebApp: {
      initData: "AUDIT_SYNTHETIC_NOT_VALID_AUTH", colorScheme: telegramColors ? "light" : theme,
      viewportStableHeight: height,
      safeAreaInset: { top: safeArea ? 24 : 0, right: 0, bottom: safeArea ? 34 : 0, left: 0 },
      contentSafeAreaInset: { top: 0, right: 0, bottom: 0, left: 0 },
      ready: noop, expand: noop, onEvent: noop, offEvent: noop,
      BackButton: { onClick: noop, offClick: noop, show: noop, hide: noop },
    } };
    if (state === "offline") {
      Object.defineProperty(navigator, "onLine", { configurable: true, get: () => false });
    }
    // Test denial, never ask for access to the developer's physical camera.
    if (navigator.mediaDevices) navigator.mediaDevices.getUserMedia = async () => { throw new DOMException("Audit camera denial", "NotAllowedError"); };
  }, { theme, height: viewport.height, telegramColors, safeArea, state });
  await page.goto(new URL(path, base).href);
  if (telegramColors) {
    await page.evaluate(() => {
      document.documentElement.style.setProperty("--tg-theme-bg-color", "#ffffff");
      document.documentElement.style.setProperty("--tg-theme-text-color", "#202623");
      document.documentElement.style.setProperty("--tg-theme-secondary-bg-color", "#f3f5f4");
    });
  }
  if (state === "loading") await page.locator(".app-content .skeleton").waitFor();
  else if (state === "error" || state === "auth-error") await page.getByRole("alert").waitFor();
  else if (path.startsWith("/food/share/")) await page.locator(".share-preview-heading").waitFor();
  else if (path === "/privacy-policy") await page.locator(".policy-page").waitFor();
  else if (state === "empty") await page.locator(".page").waitFor();
  else await page.locator(ready[section]).first().waitFor();
  if (state !== "loading") await page.locator(".skeleton").waitFor({ state: "hidden" });
  await page.evaluate(() => document.fonts.ready);
  const capture = async (name, fullPage = false) => {
    await page.mouse.move(0, 0);
    const filename = `${name}-${viewport.width}x${viewport.height}-${theme}${fullPage ? "-full" : ""}.png`;
    const metrics = await page.evaluate(() => {
      const bounds = (element) => {
        if (!element) return null;
        const rect = element.getBoundingClientRect();
        return { x: Math.round(rect.x), y: Math.round(rect.y), width: Math.round(rect.width), height: Math.round(rect.height) };
      };
      const controls = [...document.querySelectorAll("button, a, input, select, textarea, [role=button]")].filter((element) => element.getClientRects().length && getComputedStyle(element).visibility !== "hidden");
      const hitTarget = (element) => element.matches('input[type="checkbox"], input[type="radio"]') && element.closest("label") ? element.closest("label") : element;
      return {
        documentWidth: document.documentElement.scrollWidth, viewportWidth: innerWidth,
        documentHeight: document.documentElement.scrollHeight, scrollY,
        navigation: bounds(document.querySelector(".bottom-navigation")),
        meals: bounds(document.querySelector(".ration-meals")), chart: bounds(document.querySelector(".weight-chart")),
        dialog: bounds(document.querySelector('[role="alertdialog"]') ?? document.querySelector('[role="dialog"]')),
        smallControls: controls.filter((element) => { const rect = hitTarget(element).getBoundingClientRect(); return rect.width < 44 || rect.height < 44; }).map((element) => ({ label: element.getAttribute("aria-label") ?? element.textContent.trim().slice(0, 65), ...bounds(hitTarget(element)) })).slice(0, 30),
        smallInputs: controls.filter((element) => element.matches("input:not([type=checkbox]),select,textarea") && parseFloat(getComputedStyle(element).fontSize) < 16).map((element) => ({ id: element.id, fontSize: getComputedStyle(element).fontSize })),
        theme: document.documentElement.dataset.theme, background: getComputedStyle(document.body).backgroundColor,
      };
    });
    const bytes = await page.screenshot({ path: resolve(output, filename), fullPage, animations: "disabled", caret: "hide" });
    captures.push({ file: filename, route: path, state, viewport, theme, fullPage, sha256: createHash("sha256").update(bytes).digest("hex"), metrics, requests: [...new Set(requests)] });
    console.log(filename);
  };
  const close = async () => {
    for (const route of pendingRoutes) await route.abort();
    await context.close();
  };
  return { page, capture, close };
}

try {
  browser = process.env.UI_AUDIT_CDP_URL
    ? await chromium.connectOverCDP(process.env.UI_AUDIT_CDP_URL)
    : await chromium.launch({ executablePath: process.env.UI_AUDIT_EXECUTABLE || undefined });
  for (const viewport of viewports) for (const theme of ["light", "dark"]) for (const section of Object.keys(ready)) {
    const session = await openPage(section, { viewport, theme });
    await session.capture(section);
    if (viewport.width === 390) await session.capture(section, true);
    await session.close();
  }
  for (const state of ["empty", "error", "loading"]) for (const section of Object.keys(ready)) {
    const session = await openPage(section, { state });
    await session.capture(`${section}-${state}`);
    await session.close();
  }
  for (const [section, state, path] of [
    ["ration", "no-goals", "/ration"], ["ration", "populated", "/ration?date=2026-09-14"],
    ["ration", "auth-error", "/ration"], ["food", "populated", "/food/share/audit"],
    ["food", "imported", "/food/share/audit"], ["profile", "populated", "/privacy-policy"],
    ["food", "compact", "/food"],
  ]) {
    const session = await openPage(section, { state, path });
    await session.capture(`${section}-${path.includes("?") ? "future" : path.includes("share") ? `share-${state}` : path.includes("privacy") ? "privacy" : state}`);
    await session.close();
  }

  const ration = await openPage("ration", { path: "/ration/add?date=2026-09-13&meal=breakfast" });
  await ration.page.locator(".ration-source-list button").first().waitFor();
  await ration.capture("ration-picker");
  await ration.page.locator(".ration-source-list button").first().click();
  await ration.capture("ration-portion");
  // Measure focus escape without modifying the application under audit.
  await ration.page.getByRole("button", { name: "Добавить в рацион", exact: true }).focus();
  await ration.page.keyboard.press("Tab");
  diagnostics.push({ check: "sheet-tab-focus", result: await ration.page.evaluate(() => ({ insideDialog: Boolean(document.activeElement?.closest('[role="dialog"]')), focusedElement: document.activeElement?.tagName })) });
  await ration.close();

  const entry = await openPage("ration", { state: "deleted-source" });
  await entry.page.getByRole("button", { name: /^Открыть запись/ }).first().click();
  await entry.capture("ration-deleted-source");
  await entry.page.getByRole("button", { name: "Изменить", exact: true }).click();
  await entry.capture("ration-edit");
  await entry.page.getByRole("button", { name: "Назад", exact: true }).click();
  await entry.page.getByRole("button", { name: "Копировать", exact: true }).click();
  await entry.capture("ration-copy");
  await entry.close();

  for (const theme of ["light", "dark"]) {
    const food = await openPage("food", { theme });
    await food.page.getByRole("button", { name: /^Выбрать / }).first().click();
    await food.capture("food-selection");
    await food.page.getByRole("button", { name: "Поделиться", exact: true }).click();
    await food.page.locator(".share-link").waitFor();
    await food.capture("food-share-link");
    await food.page.getByRole("button", { name: "Закрыть", exact: true }).click();
    await food.page.getByRole("button", { name: "В папку", exact: true }).click();
    await food.capture("food-move");
    await food.close();
  }
  const folders = await openPage("food", { viewport: viewports[0] });
  await folders.page.getByRole("button", { name: "Управлять папками" }).click();
  await folders.capture("food-folders");
  await folders.page.getByRole("button", { name: /^Удалить Молочные/ }).click();
  await folders.capture("folder-delete");
  await folders.close();

  for (const kind of ["ingredients", "dishes"]) {
    const editor = await openPage("food", { path: `/food/new?kind=${kind}`, state: kind === "ingredients" ? "duplicate" : "populated" });
    await editor.page.getByRole("dialog").waitFor();
    if (kind === "dishes") {
      await editor.page.getByLabel("Название", { exact: true }).fill("Завтрак с йогуртом");
      await editor.page.locator(".ingredient-picker-results button").first().click();
      await editor.page.getByLabel("Найти ингредиент", { exact: true }).fill("банан");
      await editor.page.locator(".ingredient-picker-results button").filter({ hasText: "Банан" }).click();
    }
    await editor.capture(`food-editor-${kind}`);
    if (kind === "ingredients") {
      await editor.page.getByLabel("Название", { exact: true }).fill(ingredients[0].name);
      await editor.page.getByLabel("Ккал", { exact: true }).fill("62");
      await editor.page.getByLabel("Белки, г", { exact: true }).fill("4");
      await editor.page.getByLabel("Жиры, г", { exact: true }).fill("2,5");
      await editor.page.getByLabel("Углеводы, г", { exact: true }).fill("5,9");
      await editor.page.getByRole("button", { name: "Сохранить", exact: true }).click();
      await editor.page.locator(".duplicate-notice").waitFor();
      await editor.page.locator(".duplicate-notice").scrollIntoViewIfNeeded();
      await editor.capture("food-duplicate");
    }
    await editor.close();
  }

  for (const state of ["populated", "barcode-missing"]) {
    const scanner = await openPage("food", { state });
    await scanner.page.getByRole("button", { name: "Сканировать штрихкод" }).click();
    if (state === "populated") {
      await scanner.capture("barcode-manual");
      await scanner.page.getByRole("button", { name: "Включить камеру" }).click();
      await scanner.page.locator(".scanner-message").waitFor();
      await scanner.capture("barcode-denied");
    }
    await scanner.page.getByLabel("Штрихкод", { exact: true }).fill("1234567890128");
    await scanner.page.getByRole("button", { name: "Найти продукт" }).click();
    await scanner.page.locator(".barcode-review").waitFor();
    await scanner.capture(`barcode-review-${state}`);
    await scanner.close();
  }

  const weight = await openPage("weight");
  await weight.page.getByRole("button", { name: "Записать", exact: true }).click();
  await weight.capture("weight-new");
  await weight.page.getByRole("button", { name: "Закрыть", exact: true }).click();
  await weight.page.locator(".weight-history-list > button").first().click();
  await weight.page.getByRole("dialog").waitFor();
  await weight.capture("weight-edit");
  await weight.page.getByRole("button", { name: "Закрыть", exact: true }).click();
  await weight.page.getByRole("button", { name: "Изменить", exact: true }).click();
  await weight.capture("weight-goal");
  await weight.page.getByRole("button", { name: "Закрыть", exact: true }).click();
  await weight.page.getByLabel("Период графика").selectOption("custom");
  await weight.page.locator(".weight-dynamics").scrollIntoViewIfNeeded();
  await weight.capture("weight-custom-range");
  await weight.close();

  const profile = await openPage("profile");
  await profile.page.locator(".danger-zone button").click();
  await profile.capture("profile-delete-warning");
  await profile.page.getByRole("button", { name: "Продолжить", exact: true }).click();
  await profile.page.locator(".deletion-confirmation").waitFor();
  await profile.capture("profile-delete-challenge");
  await profile.close();

  const mismatch = await openPage("ration", { theme: "dark", telegramColors: true });
  await mismatch.capture("ration-telegram-light-override");
  await mismatch.close();
  const insets = await openPage("food", { safeArea: true });
  await insets.capture("food-safe-area");
  await insets.close();
  const offline = await openPage("food", { state: "offline" });
  await offline.page.locator(".connection-status.is-offline").waitFor();
  await offline.capture("food-offline-indicator");
  await offline.close();

  const longHeader = await openPage("food", { viewport: viewports[0] });
  const headerResult = await longHeader.page.evaluate(() => {
    const title = document.querySelector(".top-bar__titles small");
    const titles = document.querySelector(".top-bar__titles");
    const status = document.querySelector(".connection-status");
    if (!title || !titles || !status) throw new Error("Top bar is unavailable");
    title.textContent = "Еда · Очень длинное название пользовательского раздела продуктов";
    const titlesRect = titles.getBoundingClientRect();
    const statusRect = status.getBoundingClientRect();
    return {
      clipped: title.scrollWidth > title.clientWidth,
      clearsStatus: titlesRect.right <= statusRect.left,
      noHorizontalOverflow: document.documentElement.scrollWidth === innerWidth,
    };
  });
  diagnostics.push({ check: "long-header", result: headerResult });
  assert.deepEqual(headerResult, { clipped: true, clearsStatus: true, noHorizontalOverflow: true });
  await longHeader.capture("food-long-header");
  await longHeader.close();

  assert.deepEqual(errors, [], "Browser or unmocked API failures");
  const manifest = {
    revision: execFileSync("git", ["rev-parse", "HEAD"], { cwd: root, encoding: "utf8" }).trim(),
    browser: browser.version(), browserConnection: process.env.UI_AUDIT_CDP_URL ? "cdp" : "local", platform: process.platform, clock: NOW,
    fixtureSha256: createHash("sha256").update(await readFile(new URL("./ui-baseline-fixtures.mjs", import.meta.url))).digest("hex"),
    title: auditTitle, captures, diagnostics, errors,
  };
  await writeFile(resolve(output, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);
  const gallery = `<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${auditTitle}</title><style>body{font:14px system-ui;margin:24px;background:#eceff1;color:#202623}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:24px}figure{margin:0;min-width:0}img{width:100%;max-height:620px;object-fit:contain;object-position:top;background:#dce2df}figcaption{overflow-wrap:anywhere;padding:8px 0}a{color:#1667a8}</style><h1>${auditTitle}</h1><p>Синтетические данные. Chromium ${browser.version()}. ${captures.length} снимков. <a href="manifest.json">Метрики и запросы</a></p><main>${captures.map(({ file }) => `<figure><a href="${file}"><img src="${file}" loading="lazy" alt="${file}"></a><figcaption>${file}</figcaption></figure>`).join("")}</main></html>`;
  await writeFile(resolve(output, "index.html"), gallery);
  await writeFile(resolve(output, "run-status.json"), `${JSON.stringify({ status: "complete", captures: captures.length })}\n`);
  console.log(`Captured ${captures.length} images in ${output}`);
} catch (error) {
  await writeFile(resolve(output, "run-status.json"), `${JSON.stringify({ status: "failed", captures: captures.length })}\n`);
  throw error;
} finally {
  await browser?.close();
}
