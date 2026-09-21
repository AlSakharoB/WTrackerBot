import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import AxeBuilder from "@axe-core/playwright";

import { createFixtures, ingredients, longIngredients, mutationResponse, NOW, TODAY } from "./ui-baseline-fixtures.mjs";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const base = new URL(process.env.UI_AUDIT_URL ?? "http://127.0.0.1:5173");
assert(["localhost", "127.0.0.1", "[::1]"].includes(base.hostname), "Only a local frontend is allowed");
assert.equal(base.protocol, "http:");
const output = resolve(root, process.env.UI_AUDIT_OUTPUT ?? "docs/miniapp-redesign/screenshots/baseline");
const viewports = [{ width: 320, height: 568 }, { width: 360, height: 800 }, { width: 390, height: 844 }, { width: 430, height: 932 }, { width: 768, height: 1024 }, { width: 1280, height: 800 }];
const ready = { ration: ".ration-balance", food: ".food-row", weight: ".weight-chart-dot", profile: ".profile-summary" };
const captures = [];
const diagnostics = [];
const errors = [];
const accessibilityViolations = [];
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
      if (apiPath === "/barcodes/lookup" && state === "barcode-unavailable") return respond({ error: { message: "Open Food Facts временно недоступен. Попробуйте позже.", correlation_id: "audit-offline" } }, 503);
      if (/^\/barcodes\/[^/]+\/create-ingredient$/.test(apiPath) && state === "barcode-duplicate") return respond({ error: { message: "Этот продукт уже добавлен", details: { existing: ingredients[0] } } }, 409);
      if (state === "ration-conflict" && request.method() === "PATCH" && /^\/ration\/entries\//.test(apiPath)) {
        return respond({ error: { message: "Запись была изменена в другом сеансе", correlation_id: "audit-conflict" } }, 409);
      }
      const result = mutationResponse(apiPath, state);
      if (result !== undefined) return respond(result);
    } else {
      if (/^\/ration\/\d{4}-\d{2}-\d{2}$/.test(apiPath)) {
        const date = apiPath.split("/").at(-1);
        return respond({ ...fixtures["/ration/day"], date, is_today: date === TODAY, is_future: date > TODAY });
      }
      if (apiPath === "/weight") {
        const dateFrom = url.searchParams.get("from") ?? fixtures["/weight"].date_from;
        const dateTo = url.searchParams.get("to") ?? fixtures["/weight"].date_to;
        const allPoints = fixtures["/weight"].points;
        const visiblePoints = allPoints.filter((point) => {
          const date = point.measured_at.slice(0, 10);
          return date >= dateFrom && date <= dateTo;
        });
        return respond({
          ...fixtures["/weight"],
          date_from: dateFrom,
          date_to: dateTo,
          period_change_kg: visiblePoints.length > 1 ? String(Number(visiblePoints.at(-1).weight_kg) - Number(visiblePoints[0].weight_kg)) : null,
          minimum_kg: visiblePoints.length ? String(Math.min(...visiblePoints.map((point) => Number(point.weight_kg)))) : null,
          maximum_kg: visiblePoints.length ? String(Math.max(...visiblePoints.map((point) => Number(point.weight_kg)))) : null,
          points: visiblePoints,
          history: [...visiblePoints].reverse(),
        });
      }
      if (apiPath.endsWith("/delete-consequences")) return respond({ can_delete: false, message: "Ингредиент используется в блюде. Сначала измените состав блюда.", dependencies: ["Овсянка с йогуртом и бананом"] });
      if (apiPath === "/ingredients" && state === "long-food") {
        const search = url.searchParams.get("query")?.toLocaleLowerCase("ru-RU") ?? "";
        const filtered = longIngredients.filter((item) => item.name.toLocaleLowerCase("ru-RU").includes(search));
        const offset = Number(url.searchParams.get("cursor") ?? 0);
        const items = filtered.slice(offset, offset + 12);
        return respond({ items, next_cursor: offset + items.length < filtered.length ? String(offset + items.length) : null });
      }
      if (Object.hasOwn(fixtures, apiPath)) {
        const data = structuredClone(fixtures[apiPath]);
        const search = url.searchParams.get("query") ?? url.searchParams.get("q");
        if (data?.items && search) data.items = data.items.filter((item) => item.name.toLocaleLowerCase("ru-RU").includes(search.toLocaleLowerCase("ru-RU")));
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
  if (state === "loading") await page.locator('.product-state[aria-busy="true"], .app-content .skeleton, .app-content [aria-busy="true"]').first().waitFor();
  else if (state === "error" || state === "auth-error") await page.getByRole("alert").waitFor();
  else if (path.startsWith("/food/share/")) await page.locator(".share-preview-heading").waitFor();
  else if (path === "/privacy-policy") await page.locator(".policy-page").waitFor();
  else if (state === "empty") await page.locator(".page").waitFor();
  else await page.locator(ready[section]).first().waitFor();
  if (state !== "loading") await page.locator(".skeleton").waitFor({ state: "hidden" });
  await page.evaluate(() => document.fonts.ready);
  if (viewport.width === 390 && state === "populated" && !path.startsWith("/food/share/")) {
    const axeResult = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
    for (const violation of axeResult.violations) {
      accessibilityViolations.push({ section, path, id: violation.id, impact: violation.impact, nodes: violation.nodes.map((node) => node.target) });
    }
  }
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
        balance: bounds(document.querySelector(".ration-balance")),
        meals: bounds(document.querySelector(".ration-meals")),
        mealsHeading: bounds(document.querySelector(".ration-meals .section-heading")),
        addMealButton: bounds(document.querySelector('.ration-meals .section-heading a[href^="/ration/add"]')),
        firstMeal: bounds(document.querySelector(".ration-meals .meal-section")),
        foodHeader: bounds(document.querySelector(".food-page-heading")),
        foodSearch: bounds(document.querySelector(".food-search-sort")),
        foodFolders: bounds(document.querySelector(".food-folder-strip")),
        thirdFoodRow: bounds(document.querySelectorAll(".food-row")[2]),
        chart: bounds(document.querySelector(".weight-chart")),
        dialog: bounds(document.querySelector('[role="alertdialog"]') ?? document.querySelector('[role="dialog"]')),
        smallControls: controls.filter((element) => { const rect = hitTarget(element).getBoundingClientRect(); return rect.width < 44 || rect.height < 44; }).map((element) => ({ label: element.getAttribute("aria-label") ?? element.textContent.trim().slice(0, 65), ...bounds(hitTarget(element)) })).slice(0, 30),
        smallInputs: controls.filter((element) => element.matches("input:not([type=checkbox]),select,textarea") && parseFloat(getComputedStyle(element).fontSize) < 16).map((element) => ({ id: element.id, fontSize: getComputedStyle(element).fontSize })),
        theme: document.documentElement.dataset.theme, background: getComputedStyle(document.body).backgroundColor,
        imageFallbacks: [...document.images].filter((image) => image.complete && image.naturalWidth === 0).length,
        navVisible: Boolean(document.querySelector(".bottom-navigation")?.getBoundingClientRect().height),
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
  return { page, context, capture, close, requests };
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
    ["ration", "no-goals", "/ration"], ["ration", "single", "/ration"],
    ["ration", "partial-goals", "/ration"], ["ration", "excess", "/ration"],
    ["ration", "populated", "/ration?date=2026-09-14"],
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
  await ration.page.getByRole("button", { name: /^Добавить в / }).focus();
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

  const conflict = await openPage("ration", { state: "ration-conflict" });
  await conflict.page.getByRole("button", { name: /^Открыть запись/ }).first().click();
  await conflict.page.getByRole("button", { name: "Изменить", exact: true }).click();
  await conflict.page.getByLabel("Количество, г", { exact: true }).fill("301");
  await conflict.page.getByRole("button", { name: "Сохранить", exact: true }).click();
  await conflict.page.locator(".ration-conflict").waitFor();
  await conflict.capture("ration-conflict");
  await conflict.close();

  for (const theme of ["light", "dark"]) {
    const food = await openPage("food", { theme });
    await food.page.getByRole("button", { name: "Выбрать", exact: true }).click();
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
      await editor.page.getByRole("button", { name: "Изменить название" }).click();
      await editor.page.getByRole("button", { name: "Закрыть", exact: true }).click();
      await editor.capture("food-editor-discard");
    }
    await editor.close();
  }

  const longCatalog = await openPage("food", { state: "long-food", viewport: viewports[0] });
  await longCatalog.page.getByRole("button", { name: "Показать еще" }).click();
  await longCatalog.page.getByText(/13 загружено|24 загружено/).waitFor();
  await longCatalog.capture("food-long-catalog", true);
  await longCatalog.close();

  const noResults = await openPage("food");
  await noResults.page.getByLabel("Поиск еды").fill("несуществующий продукт");
  await noResults.page.getByText("Ничего не найдено", { exact: true }).waitFor();
  await noResults.capture("food-no-results");
  await noResults.close();

  for (const state of ["populated", "barcode-missing", "barcode-derived"]) {
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

  const notFound = await openPage("food", { state: "barcode-not-found" });
  await notFound.page.getByRole("button", { name: "Сканировать штрихкод" }).click();
  await notFound.page.getByLabel("Штрихкод", { exact: true }).fill("1234567890128");
  await notFound.page.getByRole("button", { name: "Найти продукт" }).click();
  await notFound.page.locator(".barcode-not-found").waitFor();
  await notFound.capture("barcode-not-found");
  await notFound.page.getByRole("button", { name: "Заполнить вручную" }).click();
  await notFound.capture("barcode-manual-review");
  await notFound.close();

  const unavailable = await openPage("food", { state: "barcode-unavailable" });
  await unavailable.page.getByRole("button", { name: "Сканировать штрихкод" }).click();
  await unavailable.page.getByLabel("Штрихкод", { exact: true }).fill("1234567890128");
  await unavailable.page.getByRole("button", { name: "Найти продукт" }).click();
  await unavailable.page.locator(".barcode-lookup-error").waitFor();
  await unavailable.capture("barcode-external-unavailable");
  await unavailable.close();

  const duplicateBarcode = await openPage("food", { state: "barcode-duplicate" });
  await duplicateBarcode.page.getByRole("button", { name: "Сканировать штрихкод" }).click();
  await duplicateBarcode.page.getByLabel("Штрихкод", { exact: true }).fill("1234567890128");
  await duplicateBarcode.page.getByRole("button", { name: "Найти продукт" }).click();
  await duplicateBarcode.page.locator(".barcode-review").waitFor();
  await duplicateBarcode.page.getByText(/Я проверил название/).click();
  await duplicateBarcode.page.getByRole("button", { name: "Создать ингредиент" }).click();
  await duplicateBarcode.page.locator(".duplicate-notice").waitFor();
  await duplicateBarcode.capture("barcode-duplicate");
  await duplicateBarcode.close();

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

  for (const state of ["weight-single", "weight-two", "weight-achieved", "weight-gain", "weight-no-start"]) {
    const weightState = await openPage("weight", { state });
    await weightState.capture(state);
    await weightState.close();
  }

  const historicalWeight = await openPage("weight");
  await historicalWeight.page.getByRole("button", { name: "Предыдущий период" }).click();
  await historicalWeight.page.getByText("Нет измерений за этот период").waitFor();
  await historicalWeight.capture("weight-empty-history");
  await historicalWeight.close();

  const interactiveWeight = await openPage("weight", { viewport: viewports[2] });
  const weightRequests = () => interactiveWeight.requests.filter((request) => request.startsWith("GET /api/v1/weight?"));
  const initialWeightRequests = weightRequests().length;
  const chart = interactiveWeight.page.locator(".weight-chart");
  await chart.scrollIntoViewIfNeeded();
  const chartBounds = await chart.boundingBox();
  assert(chartBounds, "Interactive weight chart bounds are unavailable");
  const centerX = chartBounds.x + chartBounds.width / 2;
  const centerY = chartBounds.y + chartBounds.height / 2;
  await interactiveWeight.page.mouse.move(centerX, centerY);
  await interactiveWeight.page.mouse.down();
  await interactiveWeight.page.mouse.move(centerX + 60, centerY + 2, { steps: 5 });
  const panMoveRequests = weightRequests().length;
  const panResponse = interactiveWeight.page.waitForResponse((response) => new URL(response.url()).pathname === "/api/v1/weight");
  await interactiveWeight.page.mouse.up();
  await panResponse;
  await interactiveWeight.page.locator(".weight-chart__loading").waitFor({ state: "hidden" });
  const panEndRequests = weightRequests().length;
  const cdp = await interactiveWeight.context.newCDPSession(interactiveWeight.page);
  const touchPoint = (x, id) => ({ x, y: centerY, id, radiusX: 4, radiusY: 4, force: 1 });
  await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [touchPoint(centerX - 60, 11), touchPoint(centerX + 60, 12)] });
  await cdp.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [touchPoint(centerX - 60, 11), touchPoint(centerX + 100, 12)] });
  const pinchMoveRequests = weightRequests().length;
  const pinchResponse = interactiveWeight.page.waitForResponse((response) => new URL(response.url()).pathname === "/api/v1/weight");
  await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  await pinchResponse;
  await interactiveWeight.page.locator(".weight-chart__loading").waitFor({ state: "hidden" });
  const pinchEndRequests = weightRequests().length;
  const interactionResult = {
    initial: initialWeightRequests,
    duringPan: panMoveRequests,
    afterPan: panEndRequests,
    duringPinch: pinchMoveRequests,
    afterPinch: pinchEndRequests,
    touchAction: await chart.evaluate((element) => getComputedStyle(element).touchAction),
    resetEnabled: await interactiveWeight.page.getByRole("button", { name: "Вернуться к текущему периоду" }).isEnabled(),
  };
  diagnostics.push({ check: "weight-window-interactions", result: interactionResult });
  assert.equal(interactionResult.duringPan, interactionResult.initial, "Pan must not request during pointermove");
  assert.equal(interactionResult.afterPan, interactionResult.initial + 1, "Pan must request once after pointerup");
  assert.equal(interactionResult.duringPinch, interactionResult.afterPan, "Pinch must not request during pointermove");
  assert.equal(interactionResult.afterPinch, interactionResult.afterPan + 1, "Pinch must request once after pointerup");
  assert.equal(interactionResult.touchAction, "pan-y", "Chart must preserve vertical page scrolling");
  assert.equal(interactionResult.resetEnabled, true, "Reset must be available outside the current window");
  const verticalBefore = weightRequests().length;
  await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [touchPoint(centerX, 21)] });
  await cdp.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [{ ...touchPoint(centerX, 21), y: centerY + 90 }] });
  await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  const verticalAfter = weightRequests().length;
  assert.equal(verticalAfter, verticalBefore, "Vertical chart gesture must not request a new range");
  const edgeBefore = weightRequests().length;
  await interactiveWeight.page.mouse.move(chartBounds.x + 4, centerY);
  await interactiveWeight.page.mouse.down();
  await interactiveWeight.page.mouse.move(chartBounds.x + 44, centerY + 1, { steps: 4 });
  await interactiveWeight.page.mouse.up();
  await interactiveWeight.page.waitForTimeout(250);
  const edgeRequests = weightRequests().length - edgeBefore;
  assert(edgeRequests >= 0 && edgeRequests <= 1, "Edge gesture must produce at most one range request");
  diagnostics.push({ check: "weight-edge-and-vertical", result: { verticalBefore, verticalAfter, edgeRequests } });
  await interactiveWeight.capture("weight-interactive-window");
  await interactiveWeight.page.getByRole("link", { name: "Профиль" }).click();
  await interactiveWeight.page.locator(".profile-summary").waitFor();
  diagnostics.push({ check: "weight-route-change-during-session", result: { pathname: new URL(interactiveWeight.page.url()).pathname } });
  await interactiveWeight.close();

  const profile = await openPage("profile");
  await profile.page.locator(".profile-danger-zone button").click();
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

  const compactRation = captures.find(({ file }) => file === "ration-320x568-light.png");
  assert(compactRation?.metrics.navigation && compactRation.metrics.mealsHeading && compactRation.metrics.addMealButton, "Compact ration metrics are unavailable");
  const compactLimit = compactRation.metrics.navigation.y;
  assert(compactRation.metrics.mealsHeading.y + compactRation.metrics.mealsHeading.height <= compactLimit, "Meals heading must be visible above navigation at 320x568");
  assert(compactRation.metrics.addMealButton.y + compactRation.metrics.addMealButton.height <= compactLimit, "Primary add action must be visible above navigation at 320x568");
  const phoneRation = captures.find(({ file }) => file === "ration-390x844-light.png");
  assert(phoneRation?.metrics.navigation && phoneRation.metrics.firstMeal, "Phone ration metrics are unavailable");
  assert(phoneRation.metrics.firstMeal.y < phoneRation.metrics.navigation.y, "First meal must begin above navigation at 390x844");
  const compactFood = captures.find(({ file }) => file === "food-320x568-light.png");
  assert(compactFood, "Compact food metrics are unavailable");
  assert.equal(compactFood.metrics.documentWidth, compactFood.metrics.viewportWidth, "Food must not overflow horizontally at 320px");
  const phoneFood = captures.find(({ file }) => file === "food-390x844-light.png");
  assert(phoneFood?.metrics.navigation && phoneFood.metrics.thirdFoodRow, "Phone food metrics are unavailable");
  assert(phoneFood.metrics.thirdFoodRow.y < phoneFood.metrics.navigation.y, "Three food rows must begin above navigation at 390x844");
  const compactWeight = captures.find(({ file }) => file === "weight-320x568-light.png");
  assert(compactWeight?.metrics.chart, "Compact weight chart metrics are unavailable");
  assert.equal(compactWeight.metrics.documentWidth, compactWeight.metrics.viewportWidth, "Weight must not overflow horizontally at 320px");

  assert.deepEqual(errors, [], "Browser or unmocked API failures");
  assert.deepEqual(accessibilityViolations, [], "Accessibility violations detected");
  const layoutDefects = captures.filter(({ metrics }) => metrics.documentWidth > metrics.viewportWidth || metrics.imageFallbacks > 0);
  assert.deepEqual(layoutDefects, [], "Visual layout or image fallback defects detected");
  const manifest = {
    revision: execFileSync("git", ["rev-parse", "HEAD"], { cwd: root, encoding: "utf8" }).trim(),
    browser: browser.version(), browserConnection: process.env.UI_AUDIT_CDP_URL ? "cdp" : "local", platform: process.platform, clock: NOW,
    fixtureSha256: createHash("sha256").update(await readFile(new URL("./ui-baseline-fixtures.mjs", import.meta.url))).digest("hex"),
    title: auditTitle, captures, diagnostics, errors, accessibilityViolations,
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
