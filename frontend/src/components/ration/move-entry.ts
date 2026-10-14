import type { MealType, RationDay, RationNutrition } from "../../api/client";

export function moveEntryInDay(day: RationDay, entryId: string, destination: MealType): RationDay {
  const entry = day.meals.flatMap((meal) => meal.entries).find((item) => item.id === entryId);
  if (!entry || entry.meal_type === destination || !day.meals.some((meal) => meal.type === destination)) return day;
  return {
    ...day,
    meals: day.meals.map((meal) => {
      if (meal.type !== entry.meal_type && meal.type !== destination) return meal;
      const entries = meal.type === destination
        ? [...meal.entries, { ...entry, meal_type: destination }]
        : meal.entries.filter((item) => item.id !== entryId);
      const sum = (key: keyof RationNutrition) => String(Math.round(entries.reduce((value, item) => value + Number(item.nutrition[key]), 0) * 1e6) / 1e6);
      const totals = { energy_kcal: sum("energy_kcal"), protein_g: sum("protein_g"), fat_g: sum("fat_g"), carbs_g: sum("carbs_g") };
      return { ...meal, entries, totals };
    }),
  };
}
