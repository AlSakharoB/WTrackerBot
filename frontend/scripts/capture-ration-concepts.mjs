import { createHash } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const baseUrl = new URL(process.env.UI_DESIGN_URL ?? "http://127.0.0.1:5173/design/ration-concepts/");
if (!["localhost", "127.0.0.1", "[::1]"].includes(baseUrl.hostname) || baseUrl.protocol !== "http:") {
  throw new Error("UI_DESIGN_URL must point to a local HTTP server");
}

const output = resolve(projectRoot, process.env.UI_DESIGN_OUTPUT ?? "docs/miniapp-redesign/screenshots/concepts");
const pages = ["ration", "food", "weight", "profile"];
const scenarios = [
  ...["a", "b"].flatMap((concept) => ["light", "dark"].flatMap((theme) => pages.map((page) => ({ concept, theme, page, sheet: false })))),
  { concept: "a", theme: "light", page: "ration", sheet: true },
  { concept: "b", theme: "light", page: "ration", sheet: true },
];
const captures = [];
const browserErrors = [];
let browser;

await mkdir(output, { recursive: true });
await writeFile(resolve(output, "run-status.json"), `${JSON.stringify({ status: "running" }, null, 2)}\n`);

try {
  browser = process.env.UI_AUDIT_CDP_URL
    ? await chromium.connectOverCDP(process.env.UI_AUDIT_CDP_URL)
    : await chromium.launch({ executablePath: process.env.UI_AUDIT_EXECUTABLE || undefined });

  for (const scenario of scenarios) {
    const context = await browser.newContext({
      viewport: { width: 390, height: 844 },
      deviceScaleFactor: 1,
      colorScheme: scenario.theme,
      locale: "ru-RU",
      timezoneId: "Europe/Moscow",
      reducedMotion: "reduce",
      hasTouch: true,
      serviceWorkers: "block",
    });
    const page = await context.newPage();
    page.on("pageerror", (error) => browserErrors.push(error.message));
    page.on("console", (message) => {
      if (message.type() === "error") browserErrors.push(message.text());
    });
    const url = new URL(baseUrl);
    url.searchParams.set("concept", scenario.concept);
    url.searchParams.set("theme", scenario.theme);
    url.searchParams.set("page", scenario.page);
    if (scenario.sheet) url.searchParams.set("sheet", "1");
    await page.goto(url.href, { waitUntil: "networkidle" });
    await page.locator("html.prototype-ready").waitFor();
    await page.evaluate(() => document.fonts.ready);

    const metrics = await page.evaluate(() => ({
      viewport: { width: innerWidth, height: innerHeight },
      document: { width: document.documentElement.scrollWidth, height: document.documentElement.scrollHeight },
      app: (() => { const rect = document.querySelector(".app").getBoundingClientRect(); return { width: rect.width, height: rect.height }; })(),
      nav: (() => { const rect = document.querySelector(".bottom-nav").getBoundingClientRect(); return { top: rect.top, bottom: rect.bottom }; })(),
      smallControls: [...document.querySelectorAll("button")]
        .filter((element) => element.getClientRects().length > 0 && getComputedStyle(element).visibility !== "hidden")
        .filter((element) => { const rect = element.getBoundingClientRect(); return rect.width < 44 || rect.height < 44; })
        .map((element) => ({ label: element.getAttribute("aria-label") ?? element.textContent.trim(), width: element.getBoundingClientRect().width, height: element.getBoundingClientRect().height })),
    }));
    const state = scenario.sheet ? "add-sheet" : scenario.page;
    const filename = `concept-${scenario.concept}-${state}-${scenario.theme}-390x844.png`;
    const bytes = await page.screenshot({ path: resolve(output, filename), animations: "disabled", caret: "hide" });
    captures.push({ ...scenario, state, viewport: "390x844", filename, sha256: createHash("sha256").update(bytes).digest("hex"), metrics });
    await context.close();
  }

  if (browserErrors.length > 0) throw new Error(`Browser errors: ${browserErrors.join(" | ")}`);
  const manifest = {
    status: "complete",
    created_at: new Date().toISOString(),
    source: "frontend/design/ration-concepts",
    browser: await browser.version(),
    captures,
    errors: browserErrors,
  };
  await writeFile(resolve(output, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);
  await writeFile(resolve(output, "run-status.json"), `${JSON.stringify({ status: "complete", captures: captures.length }, null, 2)}\n`);
  console.log(`Captured ${captures.length} Mini App concept screenshots in ${output}`);
} catch (error) {
  await writeFile(resolve(output, "run-status.json"), `${JSON.stringify({ status: "failed", error: error instanceof Error ? error.message : String(error) }, null, 2)}\n`);
  throw error;
} finally {
  await browser?.close();
}
