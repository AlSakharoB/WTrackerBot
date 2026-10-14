import { describe, expect, it } from "vitest";

import type { MealType, RationDay, RationEntry, RationNutrition } from "../../api/client";
import { moveEntryInDay } from "./move-entry";

const nutrition: RationNutrition = { energy_kcal: "90.1", protein_g: "1.2", fat_g: "0.3", carbs_g: "23.4" };
const entry: RationEntry = {
  id: "entry-1", type: "ingredient", source_id: "food-1", source_name: "Банан", source_available: true,
  grams: "100", meal_type: "breakfast", nutrition, created_at: "2026-09-13T08:00:00Z", updated_at: "2026-09-13T08:00:00Z",
};
const day: RationDay = {
  date: "2026-09-13", timezone: "UTC", number_format: "automatic", is_today: true, is_future: false,
  entry_count: 1, totals: nutrition, macro_percentages: { protein: 5, fat: 5, carbs: 90 }, goal: null,
  meals: (["breakfast", "lunch", "dinner", "snack", "other"] as MealType[]).map((type) => ({
    type, label: type, entries: type === "breakfast" ? [entry] : [],
    totals: type === "breakfast" ? nutrition : { energy_kcal: "0", protein_g: "0", fat_g: "0", carbs_g: "0" },
  })),
};

describe("optimistic meal transfers", () => {
  it("moves a single entry and recalculates both meals without changing daily nutrition", () => {
    const moved = moveEntryInDay(day, entry.id, "lunch");
    expect(moved.meals[0].entries).toEqual([]);
    expect(moved.meals[0].totals.energy_kcal).toBe("0");
    expect(moved.meals[1].entries).toEqual([{ ...entry, meal_type: "lunch" }]);
    expect(moved.meals[1].totals).toEqual(nutrition);
    expect(moved.totals).toBe(day.totals);
    expect(moved.entry_count).toBe(1);
    expect(day.meals[0].entries).toEqual([entry]);
  });

  it("does not duplicate a row when dropping it back into its own meal", () => {
    expect(moveEntryInDay(day, entry.id, "breakfast")).toBe(day);
    expect(moveEntryInDay(day, "missing", "lunch")).toBe(day);
  });

  it("keeps snapshots and grams when moving a dish whose source has been deleted", () => {
    const dish = { ...entry, type: "dish" as const, source_available: false, grams: "275" };
    const source = { ...day, meals: day.meals.map((meal) => meal.type === "breakfast" ? { ...meal, entries: [dish] } : meal) };
    const moved = moveEntryInDay(source, dish.id, "other");
    expect(moved.meals[4].entries).toEqual([{ ...dish, meal_type: "other" }]);
    expect(moved.totals).toBe(source.totals);
  });
});
