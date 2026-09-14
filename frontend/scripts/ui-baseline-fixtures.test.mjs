import { describe, expect, it } from "vitest";

import { createFixtures, dishes, ingredients, mutationResponse, NOW } from "./ui-baseline-fixtures.mjs";

describe("UI audit fixtures", () => {
  it("keeps ration totals equal to meal and entry totals", () => {
    const day = createFixtures("light")["/ration/day"];
    expect(day.entry_count).toBe(day.meals.flatMap((meal) => meal.entries).length);
    for (const key of Object.keys(day.totals)) {
      const total = day.meals.reduce((sum, meal) => sum + Number(meal.totals[key]), 0);
      expect(Number(day.totals[key])).toBeCloseTo(total, 2);
      for (const meal of day.meals) {
        expect(Number(meal.totals[key])).toBeCloseTo(meal.entries.reduce((sum, entry) => sum + Number(entry.nutrition[key]), 0), 2);
      }
    }
    expect(Object.values(day.macro_percentages).reduce((sum, value) => sum + value, 0)).toBe(100);
    expect(Number(day.totals.energy_kcal)).toBeGreaterThan(Number(day.goal.energy_kcal));
  });

  it("represents empty data, missing goals, and deleted sources separately", () => {
    const empty = createFixtures("dark", "empty");
    expect(empty["/ration/day"].entry_count).toBe(0);
    expect(empty["/weight"].points).toEqual([]);
    expect(empty["/ingredients"].items).toEqual([]);
    expect(empty["/ui-preferences"].theme_mode).toBe("dark");
    const noGoals = createFixtures("light", "no-goals")["/ration/day"];
    expect(noGoals.goal).toBeNull();
    expect(Number(noGoals.totals.protein_g)).toBeGreaterThan(0);
    const deleted = createFixtures("light", "deleted-source")["/ration/day"].meals[0].entries[0];
    expect(deleted.source_available).toBe(false);
    expect(deleted.source_id).toBeNull();
    expect(Number(deleted.nutrition.energy_kcal)).toBeGreaterThan(0);
    expect(createFixtures("light")["/ration/day"].meals[0].entries[0].source_available).toBe(true);
  });

  it("uses consistent dish weights and a nonfuture weight history", () => {
    for (const dish of dishes) {
      expect(Number(dish.total_weight_g)).toBe(dish.components.reduce((sum, component) => sum + Number(component.grams), 0));
      for (const key of Object.keys(dish.nutrition_total)) {
        const total = dish.components.reduce((sum, component) => sum + Number(component.ingredient.nutrition_per_100g[key]) * Number(component.grams) / 100, 0);
        expect(Number(dish.nutrition_total[key])).toBeCloseTo(total, 2);
        expect(Number(dish.nutrition_per_100g[key]) * Number(dish.total_weight_g) / 100).toBeCloseTo(total, 2);
      }
    }
    const weight = createFixtures("light")["/weight"];
    expect(weight.current).toEqual(weight.history[0]);
    expect(Number(weight.change_from_previous_kg)).toBeCloseTo(Number(weight.current.weight_kg) - Number(weight.previous.weight_kg), 2);
    expect(Number(weight.minimum_kg)).toBe(Math.min(...weight.points.map((point) => Number(point.weight_kg))));
    expect(weight.points.every((point) => new Date(point.measured_at) <= new Date(NOW))).toBe(true);
    expect(ingredients.every((item) => Object.values(item.nutrition_per_100g).every((value) => typeof value === "string"))).toBe(true);
  });

  it("provides distinct weight chart and goal states", () => {
    expect(createFixtures("light", "weight-single")["/weight"].points).toHaveLength(1);
    expect(createFixtures("light", "weight-two")["/weight"].points).toHaveLength(2);
    expect(createFixtures("light", "weight-achieved")["/weight"].goal.progress.achieved).toBe(true);
    expect(Number(createFixtures("light", "weight-gain")["/weight"].goal.target_weight_kg)).toBeGreaterThan(80);
    expect(createFixtures("light", "weight-no-start")["/weight"].goal.progress).toBeNull();
  });

  it("does not fabricate responses for unknown mutations", () => {
    expect(mutationResponse("/account/deletion-confirm", "populated")).toBeUndefined();
    expect(mutationResponse("/unknown", "populated")).toBeUndefined();
    const missing = mutationResponse("/barcodes/lookup", "barcode-missing");
    expect(missing.found).toBe(true);
    expect(missing.nutrition_per_100g.protein_g).toBeNull();
    const notFound = mutationResponse("/barcodes/lookup", "barcode-not-found");
    expect(notFound.found).toBe(false);
    expect(mutationResponse("/barcodes/lookup", "populated").confirmation_token).toBe("AUDIT_ONLY_CONFIRMATION_TOKEN");
  });
});
