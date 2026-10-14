import assert from "node:assert/strict";

async function swipeWeek(session, deltaX, deltaY = 0, cancel = false) {
  const bounds = await session.page.locator(".ration-week__days").boundingBox();
  assert(bounds);
  const cdp = await session.context.newCDPSession(session.page);
  const x = bounds.x + bounds.width * (deltaX > 0 ? 0.25 : 0.75);
  const y = bounds.y + bounds.height / 2;
  const point = (progress) => ({ x: x + deltaX * progress, y: y + deltaY * progress, id: 1, radiusX: 4, radiusY: 4, force: 1 });
  await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [point(0)] });
  for (const progress of [0.2, 0.4, 0.7, 1]) await cdp.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [point(progress)] });
  await cdp.send("Input.dispatchTouchEvent", { type: cancel ? "touchCancel" : "touchEnd", touchPoints: [] });
  await cdp.detach();
}

export async function auditVisualPolish(openPage, diagnostics) {
  const week = await openPage("ration");
  const weekRequests = () => week.requests.filter((request) => request.includes("/ration/week?"));
  await week.page.locator(".ration-week__activity.has-entries").first().waitFor();
  assert.equal(await week.page.locator(".ration-week__days button").count(), 7);
  assert.equal(weekRequests().length, 1);
  await week.page.locator(".ration-week__days button").first().click();
  await week.page.waitForFunction(() => document.querySelector(".ration-week__days .is-selected strong")?.textContent === "7");
  assert.equal(weekRequests().length, 1, "Selecting another day in the week must reuse its summary");
  assert.equal(await week.page.getByRole("button", { name: /^(Предыдущий|Следующий) день$/ }).count(), 0);
  await swipeWeek(week, 100);
  await week.page.waitForFunction(() => document.querySelector(".ration-week__days button strong")?.textContent === "31");
  assert.equal(await week.page.locator(".ration-week__days .is-selected strong").textContent(), "31", "A swipe must preserve the selected weekday and consume its generated click");
  assert.equal(weekRequests().length, 2, "Crossing a week boundary must load one new summary");
  await swipeWeek(week, -100);
  await week.page.waitForFunction(() => document.querySelector(".ration-week__days .is-selected strong")?.textContent === "7");
  assert.equal(weekRequests().length, 2, "Returning to a cached week must not reload its summary");
  await swipeWeek(week, -20);
  await swipeWeek(week, 5, -90);
  await swipeWeek(week, 100, 0, true);
  assert.equal(await week.page.locator(".ration-week__days .is-selected strong").textContent(), "7", "Short, vertical and cancelled gestures must not change the selected date");
  const selected = week.page.locator(".ration-week__days .is-selected");
  await selected.focus();
  await week.page.keyboard.press("ArrowRight");
  await week.page.waitForFunction(() => document.querySelector(".ration-week__days .is-selected strong")?.textContent === "14");
  assert(await selected.evaluate((element) => element === document.activeElement), "Keyboard week navigation must retain focus");
  diagnostics.push({ check: "weekly-navigation-cache", result: { requests: weekRequests() } });
  await week.capture("ration-previous-week");
  await week.close();

  const unavailable = await openPage("ration", { state: "week-error" });
  await unavailable.page.getByRole("button", { name: "Обновить данные недели" }).waitFor();
  assert.equal(await unavailable.page.locator(".macro-ring").count(), 1, "A failed weekly summary must not hide the daily ration");
  await unavailable.capture("ration-week-unavailable");
  await unavailable.close();

  const animated = await openPage("ration", { state: "gestures-no-confirm", reducedMotion: "no-preference", fixedTime: false });
  const before = await animated.page.locator(".macro-ring strong").innerText();
  await animated.page.getByRole("button", { name: /^Открыть запись/ }).first().click();
  await animated.page.waitForTimeout(350);
  await animated.page.evaluate(() => {
    window.__nutritionSamples = [];
    window.__nutritionTimer = setInterval(() => {
      const ring = document.querySelector(".macro-ring");
      window.__nutritionSamples.push({ text: ring?.querySelector("strong")?.textContent, background: ring?.style.background });
    }, 16);
  });
  await animated.page.getByRole("button", { name: "Удалить", exact: true }).click();
  await animated.page.waitForTimeout(600);
  const after = await animated.page.locator(".macro-ring strong").innerText();
  const samples = await animated.page.evaluate(() => { clearInterval(window.__nutritionTimer); return window.__nutritionSamples; });
  assert.notEqual(before, after);
  assert(samples.some((sample) => sample.text !== before && sample.text !== after), "Calories must transition through intermediate values");
  assert(new Set(samples.map((sample) => sample.background)).size > 2, "Donut segments must transition through intermediate positions");
  assert.equal(await animated.page.locator(".ration-week__days button.is-selected i.has-entries").count(), 1);
  diagnostics.push({ check: "nutrition-data-change-animation", result: { before, after, distinctValues: new Set(samples.map((sample) => sample.text)).size } });
  await animated.capture("ration-animated-update");
  await animated.close();

  const catalog = await openPage("food", { state: "gestures-no-confirm", reducedMotion: "no-preference", fixedTime: false });
  const rows = catalog.page.locator(".food-list > .swipe-row");
  const count = await rows.count();
  assert(count > 1);
  await rows.nth(1).evaluate((element) => { element.dataset.auditRemainingRow = "true"; });
  const first = await catalog.page.locator(".food-row__content").first().boundingBox();
  assert(first);
  await catalog.page.mouse.move(first.x + first.width * 0.8, first.y + first.height / 2);
  await catalog.page.mouse.down();
  await catalog.page.mouse.move(first.x + first.width * 0.2, first.y + first.height / 2, { steps: 8 });
  await catalog.page.mouse.up();
  await catalog.page.locator('.swipe-row[data-open="true"] .swipe-row__delete').waitFor();
  await catalog.page.evaluate(() => {
    window.__rowSamples = [];
    window.__rowTimer = setInterval(() => {
      const row = document.querySelector('[data-audit-remaining-row="true"]');
      if (row) window.__rowSamples.push({ y: row.getBoundingClientRect().y, transform: getComputedStyle(row).transform });
    }, 16);
  });
  await catalog.page.locator('.swipe-row[data-open="true"] .swipe-row__delete').click();
  await catalog.page.waitForTimeout(700);
  const rowSamples = await catalog.page.evaluate(() => { clearInterval(window.__rowTimer); return window.__rowSamples; });
  assert.equal(await rows.count(), count - 1);
  assert(rowSamples.some((sample) => sample.transform !== "none"), "Remaining rows must animate into the deletion gap");
  diagnostics.push({ check: "catalog-delete-layout-animation", result: { positions: new Set(rowSamples.map((sample) => Math.round(sample.y))).size } });
  await catalog.capture("food-animated-delete");
  await catalog.close();

  const chart = await openPage("weight", { theme: "dark" });
  await chart.page.locator(".weight-chart").scrollIntoViewIfNeeded();
  const area = chart.page.locator(".recharts-area-area");
  await area.waitFor();
  assert((await area.getAttribute("d"))?.length > 50, "Weight area must render a nonblank series");
  assert.equal(await chart.page.locator(".weight-chart-halo").count(), 1);
  await chart.page.locator(".weight-chart-point").last().click();
  await chart.page.locator(".weight-chart-point.is-selected").waitFor();
  assert.equal(await chart.page.locator(".weight-chart-point.is-selected").count(), 1);
  await chart.page.locator(".weight-period-stats").waitFor();
  await chart.capture("weight-polished-selection");
  await chart.page.locator(".weight-tooltip--selected").getByRole("button", { name: "Изменить", exact: true }).click();
  await chart.page.getByRole("dialog", { name: "Изменить измерение" }).waitFor();
  await chart.capture("weight-polished-edit");
  await chart.close();
}
