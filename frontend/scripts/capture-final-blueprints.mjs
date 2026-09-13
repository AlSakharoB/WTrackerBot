import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const baseUrl = new URL(process.env.UI_DESIGN_URL ?? "http://127.0.0.1:5173/design/ration-concepts/");
if (!["localhost", "127.0.0.1", "[::1]"].includes(baseUrl.hostname) || baseUrl.protocol !== "http:") {
  throw new Error("UI_DESIGN_URL must point to a local HTTP server");
}

const output = resolve(projectRoot, process.env.UI_DESIGN_OUTPUT ?? "docs/miniapp-redesign/screenshots/final");
const mobile = { width: 390, height: 844 };
const scenarios = [
  { file: "ration-light-390x844.png", page: "ration", state: "populated", theme: "light", viewport: mobile },
  { file: "ration-dark-390x844.png", page: "ration", state: "populated", theme: "dark", viewport: mobile },
  { file: "food-light-390x844.png", page: "food", state: "populated", theme: "light", viewport: mobile },
  { file: "barcode-review-light-390x844.png", page: "barcode", state: "found-derived", theme: "light", viewport: mobile },
  { file: "weight-light-390x844.png", page: "weight", state: "populated", theme: "light", viewport: mobile },
  { file: "weight-dark-390x844.png", page: "weight", state: "populated", theme: "dark", viewport: mobile },
  { file: "profile-light-390x844.png", page: "profile", state: "populated", theme: "light", viewport: mobile },
  { file: "desktop-1280x800.png", page: "ration", state: "populated", theme: "light", viewport: { width: 1280, height: 800 } },
];
const captures = [];
const errors = [];
let browser;

await mkdir(output, { recursive: true });
await writeFile(resolve(output, "run-status.json"), `${JSON.stringify({ status: "running" }, null, 2)}\n`);

try {
  browser = process.env.UI_AUDIT_CDP_URL
    ? await chromium.connectOverCDP(process.env.UI_AUDIT_CDP_URL)
    : await chromium.launch({ executablePath: process.env.UI_AUDIT_EXECUTABLE || undefined });

  for (const scenario of scenarios) {
    const context = await browser.newContext({
      viewport: scenario.viewport,
      deviceScaleFactor: 1,
      colorScheme: scenario.theme,
      locale: "ru-RU",
      timezoneId: "Europe/Moscow",
      reducedMotion: "reduce",
      hasTouch: scenario.viewport.width < 800,
      serviceWorkers: "block",
    });
    const page = await context.newPage();
    page.on("pageerror", (error) => errors.push(`${scenario.file}: ${error.message}`));
    page.on("console", (message) => {
      if (message.type() === "error") errors.push(`${scenario.file}: ${message.text()}`);
    });
    await context.route("**/*", (route) => {
      const url = new URL(route.request().url());
      return url.origin === baseUrl.origin ? route.continue() : route.abort();
    });

    const url = new URL(baseUrl);
    url.searchParams.set("concept", "selected");
    url.searchParams.set("page", scenario.page);
    url.searchParams.set("theme", scenario.theme);
    await page.goto(url.href, { waitUntil: "networkidle" });
    await page.locator("html.prototype-ready").waitFor();
    await page.evaluate(async () => {
      await document.fonts.ready;
      await Promise.all([...document.images].map((item) => item.complete ? undefined : new Promise((resolve) => item.addEventListener("load", resolve, { once: true }))));
    });

    const metrics = await page.evaluate(() => {
      const rect = (selector) => {
        const element = document.querySelector(selector);
        if (!element) return null;
        const bounds = element.getBoundingClientRect();
        return { left: bounds.left, top: bounds.top, right: bounds.right, bottom: bounds.bottom, width: bounds.width, height: bounds.height };
      };
      const controls = [...document.querySelectorAll("button, a, input, select, textarea")]
        .filter((element) => element.getClientRects().length > 0 && getComputedStyle(element).visibility !== "hidden");
      return {
        viewport: { width: innerWidth, height: innerHeight },
        document: { width: document.documentElement.scrollWidth, height: document.documentElement.scrollHeight },
        app: rect(".app"),
        navigation: rect(".bottom-nav"),
        firstMeal: rect(".selected-meals .compact-meal"),
        productImage: (() => { const image = document.querySelector(".product-photo img"); return image ? { complete: image.complete, naturalWidth: image.naturalWidth, naturalHeight: image.naturalHeight } : null; })(),
        smallControls: controls
          .filter((element) => {
            if (element.matches('input[type="checkbox"]') && element.closest("label")) return false;
            const bounds = element.getBoundingClientRect();
            return bounds.width < 44 || bounds.height < 44;
          })
          .map((element) => ({ label: element.getAttribute("aria-label") ?? element.textContent.trim().slice(0, 80), ...rectElement(element) })),
      };

      function rectElement(element) {
        const bounds = element.getBoundingClientRect();
        return { width: bounds.width, height: bounds.height };
      }
    });
    const bytes = await page.screenshot({ path: resolve(output, scenario.file), animations: "disabled", caret: "hide" });
    captures.push({ ...scenario, concept: "A + macro ring from B", created_for: "final blueprint", sha256: createHash("sha256").update(bytes).digest("hex"), metrics });
    await context.close();
  }

  if (errors.length > 0) throw new Error(`Browser errors: ${errors.join(" | ")}`);
  const revision = execFileSync("git", ["rev-parse", "--short", "HEAD"], { cwd: projectRoot, encoding: "utf8" }).trim();
  const manifest = {
    status: "complete",
    created_at: new Date().toISOString(),
    design_date: "2026-09-13",
    source: "frontend/design/ration-concepts",
    concept: "A + macro ring from B",
    revision,
    browser: await browser.version(),
    captures,
    errors,
  };
  await writeFile(resolve(output, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);
  await writeFile(resolve(output, "run-status.json"), `${JSON.stringify({ status: "complete", captures: captures.length }, null, 2)}\n`);
  console.log(`Captured ${captures.length} final blueprint screenshots in ${output}`);
} catch (error) {
  await writeFile(resolve(output, "run-status.json"), `${JSON.stringify({ status: "failed", error: error instanceof Error ? error.message : String(error) }, null, 2)}\n`);
  throw error;
} finally {
  await browser?.close();
}
