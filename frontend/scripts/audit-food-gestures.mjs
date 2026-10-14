import assert from "node:assert/strict";

async function touchSwipe(session, locator, reverse = false) {
  await locator.evaluate((element) => element.scrollIntoView({ block: "center", inline: "nearest", behavior: "instant" }));
  const rect = await locator.boundingBox();
  assert(rect);
  const cdp = await session.context.newCDPSession(session.page);
  const x = rect.x + rect.width * (reverse ? 0.3 : 0.8);
  const y = rect.y + rect.height / 2;
  const point = (dx) => ({ x: x + dx, y, id: 1, radiusX: 4, radiusY: 4, force: 1 });
  await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [point(0)] });
  for (const distance of [15, 35, 65, 90]) await cdp.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [point(reverse ? distance : -distance)] });
  await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  await cdp.detach();
}

async function dragEntry(session, mode, destination = "lunch", cancel = false) {
  const { page, context } = session;
  await page.locator(".ration-meals").evaluate((element) => element.scrollIntoView({ block: "start", behavior: "instant" }));
  const source = page.locator('[data-entry-id="entry-1"] .meal-entry__main');
  const rect = await source.boundingBox();
  assert(rect);
  const x = rect.x + rect.width / 2;
  const y = rect.y + rect.height / 2;
  let cdp;
  const point = (x, y) => ({ x, y, id: 1, radiusX: 4, radiusY: 4, force: 1 });
  if (mode === "touch") {
    cdp = await context.newCDPSession(page);
    await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [point(x, y)] });
  } else if (mode === "mouse") {
    await page.mouse.move(x, y);
    await page.mouse.down();
  } else {
    await source.focus();
    await page.keyboard.press("Space");
  }
  await page.locator(".meal-entry-drag-preview").waitFor();
  assert.equal(session.mutations.length, 0, "Holding must not mutate an entry");
  assert.equal(await page.getByRole("dialog").count(), 0, "Holding a ration row must not open its editor");
  if (cancel) {
    if (cdp) await cdp.send("Input.dispatchTouchEvent", { type: "touchCancel", touchPoints: [] });
    else { await page.keyboard.press("Escape"); if (mode === "mouse") await page.mouse.up(); }
  } else {
    const target = page.locator(`[data-meal="${destination}"]`);
    if (mode === "keyboard") {
      for (let index = 0; index < 5 && !(await target.evaluate((element) => element.classList.contains("is-drop-target"))); index++) {
        await page.keyboard.press("ArrowDown");
        await page.waitForTimeout(50);
      }
      assert(await target.evaluate((element) => element.classList.contains("is-drop-target")), "Keyboard must select the destination meal");
    } else {
      const bounds = await target.boundingBox();
      assert(bounds);
      if (cdp) await cdp.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [point(bounds.x + bounds.width / 2, bounds.y + 25)] });
      else await page.mouse.move(bounds.x + bounds.width / 2, bounds.y + 25, { steps: 8 });
      await page.waitForFunction((meal) => document.querySelector(`[data-meal="${meal}"]`)?.classList.contains("is-drop-target"), destination);
    }
    await session.capture(`ration-drag-${mode}`, false, { keepPointer: true });
    if (cdp) await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
    else if (mode === "mouse") await page.mouse.up();
    else await page.keyboard.press("Space");
  }
  await cdp?.detach();
  await page.locator(".meal-entry-drag-preview").waitFor({ state: "hidden" });
}

export async function auditFoodGestures(openPage, diagnostics) {
  // Use the real document timeline when measuring Web Animations progress.
  const animated = await openPage("food", { reducedMotion: "no-preference", fixedTime: false });
  await animated.page.getByRole("button", { name: "Управлять папками" }).click();
  const sheet = animated.page.locator(".bottom-sheet");
  const initial = await sheet.boundingBox();
  await animated.page.waitForTimeout(350);
  const settled = await sheet.boundingBox();
  assert(initial && settled && initial.y > settled.y + 5, "A menu must slide in through intermediate positions");
  await animated.page.getByRole("button", { name: "Закрыть", exact: true }).click();
  await animated.page.locator('.sheet-backdrop[data-state="closing"]').waitFor();
  await animated.page.waitForTimeout(80);
  const closing = await sheet.boundingBox();
  assert(closing && closing.y > settled.y + 5 && closing.y < 800, `A closing menu must slide down before unmounting: ${JSON.stringify({ initial, settled, closing })}`);
  assert(await animated.page.evaluate(() => document.body.dataset.overlayOpen === "true"), "The background must stay locked throughout exit");
  await sheet.waitFor({ state: "hidden" });
  assert(await animated.page.evaluate(() => !document.body.dataset.overlayOpen));
  diagnostics.push({ check: "menu-enter-and-exit-animation", result: { initial, settled, closing } });
  await animated.page.locator(".food-row__content").first().click();
  await animated.page.waitForTimeout(350);
  await animated.page.locator(".food-editor .sheet-actions button").filter({ hasText: "Удалить" }).click();
  await animated.page.getByRole("alertdialog", { name: "Удаление недоступно" }).waitFor();
  await animated.page.waitForTimeout(300);
  await animated.page.getByRole("button", { name: "Понятно", exact: true }).click();
  await animated.page.waitForTimeout(80);
  const opacity = await animated.page.locator(".dialog-backdrop").evaluate((element) => Number(getComputedStyle(element).opacity));
  assert(opacity > 0 && opacity < 1, "Confirmation must fade out before unmounting");
  await animated.page.locator(".dialog-backdrop").waitFor({ state: "hidden" });
  assert(await animated.page.evaluate(() => document.body.dataset.overlayOpen === "true"), "Closing a confirmation must keep its parent sheet locked");
  const editorBounds = await sheet.boundingBox();
  await animated.page.getByRole("button", { name: "Закрыть", exact: true }).click();
  await animated.page.waitForTimeout(80);
  const editorClosing = await sheet.boundingBox();
  assert(editorBounds && editorClosing && editorClosing.y > editorBounds.y + 5, "Conditionally mounted editors must also animate out");
  await sheet.waitFor({ state: "hidden" });
  assert(await animated.page.evaluate(() => !document.body.dataset.overlayOpen));
  diagnostics.push({ check: "conditional-editor-and-confirmation-exit", result: { opacity, editorBounds, editorClosing } });
  await animated.close();

  for (const mode of ["touch", "mouse", "keyboard"]) {
    const session = await openPage("ration", { viewport: mode === "mouse" ? { width: 1280, height: 800 } : { width: 390, height: 844 } });
    const calories = await session.page.locator(".macro-ring strong").textContent();
    await dragEntry(session, mode);
    await session.page.locator('[data-meal="lunch"] [data-entry-id="entry-1"]').waitFor();
    assert.equal(session.mutations.length, 1);
    assert.equal(session.mutations[0].method, "PATCH");
    assert.deepEqual(Object.keys(session.mutations[0].body).sort(), ["expected_updated_at", "meal_type"]);
    assert.equal(session.mutations[0].body.meal_type, "lunch");
    assert.equal(await session.page.locator(".macro-ring strong").textContent(), calories, "Transfer must preserve daily calories");
    assert.deepEqual(await session.page.evaluate(() => window.__auditHaptics), ["selection", "success"], "Transfer must acknowledge pickup and successful saving");
    await session.capture(`ration-moved-${mode}`);
    diagnostics.push({ check: `ration-transfer-${mode}`, result: session.mutations });
    await session.close();
  }

  const cancelled = await openPage("ration");
  await dragEntry(cancelled, "touch", "lunch", true);
  assert.equal(cancelled.mutations.length, 0);
  assert.equal(await cancelled.page.locator('[data-meal="breakfast"] [data-entry-id="entry-1"]').count(), 1);
  await cancelled.close();

  const conflict = await openPage("ration", { state: "ration-move-conflict" });
  await dragEntry(conflict, "mouse");
  await conflict.page.getByText(/Запись уже изменилась/).waitFor();
  await conflict.page.locator('[data-meal="breakfast"] [data-entry-id="entry-1"]').waitFor();
  assert.equal(await conflict.page.locator('[data-meal="lunch"] [data-entry-id="entry-1"]').count(), 0);
  await conflict.capture("ration-transfer-conflict");
  await conflict.close();

  const ration = await openPage("ration");
  await touchSwipe(ration, ration.page.locator(".meal-entry__main").first());
  await ration.page.locator('.meal-entry-source .swipe-row[data-open="true"]').waitFor();
  assert.equal(ration.mutations.length, 0);
  await ration.capture("ration-swipe-delete");
  await ration.page.locator('.swipe-row[data-open="true"] .swipe-row__delete').click();
  await ration.page.getByRole("alertdialog").waitFor();
  assert.equal(ration.mutations.length, 0, "Swipe must still require confirmation");
  await ration.page.getByRole("button", { name: "Удалить", exact: true }).click();
  await ration.page.locator('[data-entry-id="entry-1"]').waitFor({ state: "hidden" });
  assert.equal(ration.mutations.length, 1);
  assert.equal(ration.mutations[0].method, "DELETE");
  await ration.close();

  for (const kind of ["ingredients", "dishes"]) {
    const food = await openPage("food", { state: "gesture-delete-allowed" });
    if (kind === "dishes") await food.page.getByRole("button", { name: "Блюда", exact: true }).click();
    const count = await food.page.locator(".food-row").count();
    await touchSwipe(food, food.page.locator(".food-row__content").first());
    await food.page.locator('.swipe-row[data-open="true"]').waitFor();
    await food.capture(`food-swipe-${kind}`);
    assert.equal(food.mutations.length, 0);
    await food.page.locator('.swipe-row[data-open="true"] .swipe-row__delete').click();
    await food.page.getByRole("alertdialog").waitFor();
    await food.page.getByRole("button", { name: "Удалить", exact: true }).click();
    await food.page.waitForFunction((expected) => document.querySelectorAll(".food-row").length === expected, count - 1);
    assert.equal(food.mutations.length, 1);
    assert.equal(food.mutations[0].method, "DELETE");
    await food.close();
  }

  const blocked = await openPage("food");
  await touchSwipe(blocked, blocked.page.locator(".food-row__content").first());
  await blocked.page.locator('.swipe-row[data-open="true"] .swipe-row__delete').click();
  await blocked.page.getByRole("alertdialog", { name: "Удаление недоступно" }).waitFor();
  assert.equal(blocked.mutations.length, 0, "Ingredients used in a dish cannot be deleted by swiping");
  await blocked.capture("food-swipe-delete-blocked");
  await blocked.close();

  const held = await openPage("food");
  const cdp = await held.context.newCDPSession(held.page);
  const rect = await held.page.locator(".food-row__content").first().boundingBox();
  assert(rect);
  await cdp.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x: rect.x + 80, y: rect.y + rect.height / 2, id: 1 }] });
  await held.page.getByRole("dialog", { name: "Изменить ингредиент" }).waitFor();
  await cdp.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  assert.equal(await held.page.getByRole("dialog").count(), 1);
  assert.equal(held.mutations.length, 0);
  await held.capture("food-long-press-editor");
  await held.close();

  const scroll = await openPage("food");
  const first = scroll.page.locator(".food-row__content").first();
  await first.evaluate((element) => element.scrollIntoView({ block: "center", behavior: "instant" }));
  const before = await scroll.page.locator(".app-content").evaluate((element) => element.scrollTop);
  const row = await first.boundingBox();
  assert(row);
  const scrollCDP = await scroll.context.newCDPSession(scroll.page);
  const point = (dy) => ({ x: row.x + row.width / 2, y: row.y + row.height / 2 + dy, id: 1 });
  await scrollCDP.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [point(0)] });
  for (const dy of [-15, -35, -65, -100]) await scrollCDP.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [point(dy)] });
  await scrollCDP.send("Input.dispatchTouchEvent", { type: "touchEnd", touchPoints: [] });
  await scroll.page.waitForFunction((initial) => document.querySelector(".app-content").scrollTop > initial + 10, before);
  assert.equal(await scroll.page.locator('.swipe-row[data-open="true"]').count(), 0);
  assert.equal(await scroll.page.getByRole("dialog").count(), 0);
  await scroll.close();

  const autoScroll = await openPage("ration");
  await autoScroll.page.locator(".ration-meals").evaluate((element) => element.scrollIntoView({ block: "start", behavior: "instant" }));
  const source = await autoScroll.page.locator('[data-entry-id="entry-1"] .meal-entry__main').boundingBox();
  assert(source);
  const autoCDP = await autoScroll.context.newCDPSession(autoScroll.page);
  await autoCDP.send("Input.dispatchTouchEvent", { type: "touchStart", touchPoints: [{ x: source.x + 80, y: source.y + source.height / 2, id: 1 }] });
  await autoScroll.page.locator(".meal-entry-drag-preview").waitFor();
  const scrollBefore = await autoScroll.page.locator(".app-content").evaluate((element) => element.scrollTop);
  const content = await autoScroll.page.locator(".app-content").boundingBox();
  assert(content);
  await autoCDP.send("Input.dispatchTouchEvent", { type: "touchMove", touchPoints: [{ x: source.x + 80, y: content.y + content.height - 8, id: 1 }] });
  await autoScroll.page.waitForFunction((initial) => document.querySelector(".app-content").scrollTop > initial + 10, scrollBefore);
  await autoCDP.send("Input.dispatchTouchEvent", { type: "touchCancel", touchPoints: [] });
  await autoScroll.page.locator(".meal-entry-drag-preview").waitFor({ state: "hidden" });
  assert.equal(autoScroll.mutations.length, 0);
  diagnostics.push({ check: "vertical-scroll-and-drag-autoscroll", result: "native scroll and drag autoscroll preserved" });
  await autoScroll.close();
  diagnostics.push({ check: "list-swipe-and-hold", result: "ration, ingredients, dishes, blocked deletion and catalog hold passed" });
}
