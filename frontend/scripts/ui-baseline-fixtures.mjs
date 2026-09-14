// Synthetic API responses only. Never use real accounts, tokens, or exports here.
export const NOW = "2026-09-13T09:00:00.000Z";
export const TODAY = NOW.slice(0, 10);
const timestamps = { created_at: NOW, updated_at: NOW };
const nutrition = (energy, protein, fat, carbs) => Object.fromEntries(
  ["energy_kcal", "protein_g", "fat_g", "carbs_g"].map((key, i) => [key, String([energy, protein, fat, carbs][i])]),
);
const zero = nutrition(0, 0, 0, 0);
const sum = (values) => Object.fromEntries(Object.keys(zero).map((key) => [
  key, values.reduce((total, value) => total + Number(value[key]), 0).toFixed(2),
]));
export const ingredients = [
  ["Йогурт натуральный 2,5% без добавленного сахара", 62, 4, 2.5, 5.9, "dairy"],
  ["Банан", 89, 1.1, 0.3, 22.8, "fruit"],
  ["Овсяные хлопья цельнозерновые", 370, 13, 7, 62, null],
  ["Творог 5%", 121, 17, 5, 1.8, "dairy"],
  ["Яблоко зелёное", 52, 0.3, 0.2, 14, "fruit"],
  ["Хлеб цельнозерновой с семенами подсолнечника и тыквы", 250, 9, 7, 38, null],
  ["Молоко 2,5%", 52, 3, 2.5, 4.7, "dairy"],
  ["Огурец", 15, 0.8, 0.1, 2.8, null],
].map(([name, energy, protein, fat, carbs, folder], i) => ({
  id: `ingredient-${i + 1}`, name, nutrition_per_100g: nutrition(energy, protein, fat, carbs),
  folder_id: folder, package_weight_g: i === 0 ? "150" : null,
  photo_url: null, source_name: null, source_url: null, ...timestamps,
}));
export const longIngredients = Array.from({ length: 32 }, (_, i) => ({
  ...ingredients[i % ingredients.length],
  id: `long-ingredient-${i + 1}`,
  name: `${ingredients[i % ingredients.length].name} ${i + 1}`,
}));
export const dishes = [{
  id: "dish-1", name: "Овсянка с йогуртом и бананом", total_weight_g: "300",
  nutrition_total: nutrition(367, 13.6, 7.55, 62.65),
  nutrition_per_100g: nutrition(122.333333, 4.533333, 2.516667, 20.883333), folder_id: null,
  components: [{ ingredient: ingredients[2], grams: "50" }, { ingredient: ingredients[0], grams: "150" }, { ingredient: ingredients[1], grams: "100" }], ...timestamps,
}];
const folders = ["Молочные продукты", "Фрукты"].map((name, i) => ({
  id: i === 0 ? "dairy" : "fruit", name, sort_order: i, item_count: i === 0 ? 3 : 2,
  ingredient_count: i === 0 ? 3 : 2, dish_count: 0, ...timestamps,
}));
const user = {
  id: "audit-user", telegram_id: "1000000000001", username: "demo_audit",
  first_name: "Александра", last_name: "Тестовая", language_code: "ru",
  timezone: "Europe/Moscow", app_version: "audit-fixture",
};
const goal = { id: "nutrition-goal", ...nutrition(1000, 80, 25, 130), effective_from: "2026-09-01", effective_to: null };
const entries = [
  [dishes[0], "300", "breakfast"], [ingredients[0], "150", "breakfast"],
  [ingredients[3], "250", "lunch"], [ingredients[5], "130", "lunch"],
  [ingredients[4], "170", "snack"],
].map(([source, grams, meal], i) => ({
  id: `entry-${i + 1}`, type: source.components ? "dish" : "ingredient", source_id: source.id,
  source_available: true, source_name: source.name, grams, meal_type: meal,
  nutrition: Object.fromEntries(Object.entries(source.nutrition_per_100g).map(([key, value]) => [key, (Number(value) * Number(grams) / 100).toFixed(2)])), ...timestamps,
}));
const points = Array.from({ length: 14 }, (_, i) => ({
  id: `weight-${i + 1}`, weight_kg: (82.4 - i * 0.11 + [0, 0.15, -0.12][i % 3]).toFixed(2),
  measured_at: `2026-09-${String(i === 13 ? 13 : i + 1).padStart(2, "0")}T${i === 13 ? "08" : "05"}:30:00Z`,
  moving_average_7d_kg: i < 2 ? null : (82.45 - i * 0.1).toFixed(2),
  note: i === 13 ? "После завтрака, повторное измерение" : null, updated_at: NOW,
}));
const weightGoal = {
  id: "weight-goal", target_weight_kg: "75", start_weight_kg: "84", target_date: "2026-12-01",
  current_weight_kg: points.at(-1).weight_kg,
  progress: { percentage: "32", completed_kg: "2.88", remaining_kg: "6.12", achieved: false }, updated_at: NOW,
};

export function createFixtures(theme, state = "populated") {
  const empty = state === "empty";
  const weightPoints = empty
    ? []
    : state === "weight-single"
      ? points.slice(-1)
      : state === "weight-two"
        ? points.slice(-2)
        : points;
  const currentWeight = weightPoints.at(-1) ?? null;
  const previousWeight = weightPoints.at(-2) ?? null;
  const activeWeightGoal = empty
    ? null
    : state === "weight-achieved"
      ? { ...weightGoal, target_weight_kg: currentWeight.weight_kg, current_weight_kg: currentWeight.weight_kg, progress: { percentage: "100", completed_kg: "2.93", remaining_kg: "0", achieved: true } }
      : state === "weight-gain"
        ? { ...weightGoal, start_weight_kg: "78", target_weight_kg: "86", current_weight_kg: currentWeight.weight_kg, progress: { percentage: "38.38", completed_kg: "3.07", remaining_kg: "4.93", achieved: false } }
        : state === "weight-no-start"
          ? { ...weightGoal, start_weight_kg: null, current_weight_kg: currentWeight.weight_kg, progress: null }
          : weightGoal;
  const rationEntries = empty ? [] : structuredClone(state === "single" ? entries.slice(0, 1) : entries);
  if (state === "deleted-source") Object.assign(rationEntries[0], { source_id: null, source_available: false });
  const totals = sum(rationEntries.map((entry) => entry.nutrition));
  const macroEnergy = Number(totals.protein_g) * 4 + Number(totals.fat_g) * 9 + Number(totals.carbs_g) * 4;
  const protein = macroEnergy ? Math.round(Number(totals.protein_g) * 400 / macroEnergy) : 0;
  const fat = macroEnergy ? Math.round(Number(totals.fat_g) * 900 / macroEnergy) : 0;
  const rationGoal = empty || state === "no-goals"
    ? null
    : state === "partial-goals"
      ? { ...goal, fat_g: null, carbs_g: null }
      : state === "excess"
        ? { ...goal, energy_kcal: "700" }
        : goal;
  return {
    "/me": user,
    "/ui-preferences": { theme_mode: theme, default_section: "ration", default_weight_unit: "kg", compact_lists: state === "compact", updated_at: NOW },
    "/profile": { ...user, photo_url: null, number_format: "automatic", after_food_add_action: "open_today", confirm_deletions: true, reminders_enabled: !empty },
    "/profile/stats": Object.fromEntries(Object.entries({ diary_days: 42, ingredients: 8, dishes: 1, diary_entries: 210, weight_entries: 14, active_weight_goals: 1, share_packages: 2, imported_packages: 1 }).map(([key, value]) => [key, empty ? 0 : value])),
    "/goals/nutrition": rationGoal,
    "/reminders": empty ? [] : ["weigh_in", "nutrition"].map((type, i) => ({ id: `reminder-${i}`, type, enabled: i === 0, time_local: i === 0 ? "08:00" : "20:00", weekdays: [0, 1, 2, 3, 4, 5, 6], updated_at: NOW })),
    "/ration/day": {
      date: TODAY, timezone: user.timezone, number_format: "automatic", is_today: true, is_future: false,
      entry_count: rationEntries.length, totals,
      macro_percentages: { protein, fat, carbs: macroEnergy ? 100 - protein - fat : 0 },
      goal: rationGoal,
      meals: ["Завтрак", "Обед", "Ужин", "Перекус", "Другое"].map((label, i) => {
        const type = ["breakfast", "lunch", "dinner", "snack", "other"][i];
        const mealEntries = rationEntries.filter((entry) => entry.meal_type === type);
        return { type, label, entries: mealEntries, totals: sum(mealEntries.map((entry) => entry.nutrition)) };
      }),
    },
    "/ration/sources": { items: empty ? [] : [...ingredients, ...dishes].map((item) => ({ id: item.id, type: item.components ? "dish" : "ingredient", name: item.name, default_grams: "100", nutrition_per_100g: item.nutrition_per_100g, usage_count: 4, last_used_at: NOW })) },
    "/weight": {
      timezone: user.timezone, date_from: "2026-08-15", date_to: TODAY,
      current: currentWeight, previous: previousWeight,
      change_from_previous_kg: previousWeight ? String(Number(currentWeight.weight_kg) - Number(previousWeight.weight_kg)) : null,
      period_change_kg: weightPoints.length > 1 ? String(Number(currentWeight.weight_kg) - Number(weightPoints[0].weight_kg)) : null,
      minimum_kg: weightPoints.length ? String(Math.min(...weightPoints.map((point) => Number(point.weight_kg)))) : null,
      maximum_kg: weightPoints.length ? String(Math.max(...weightPoints.map((point) => Number(point.weight_kg)))) : null,
      goal: activeWeightGoal, points: weightPoints, history: [...weightPoints].reverse(),
    },
    "/goals/weight": activeWeightGoal,
    "/ingredients": { items: empty ? [] : ingredients, next_cursor: null },
    "/dishes": { items: empty ? [] : dishes, next_cursor: null },
    "/food-folders": { items: empty ? [] : folders },
    "/sharing/packages/audit/preview": {
      package_id: "audit-package", type: "dishes", item_count: 1, is_owner: false,
      already_imported: state === "imported", expires_at: "2026-10-01T00:00:00Z",
      ingredients: ingredients.slice(0, 3).map((item, i) => ({ key: item.id, name: item.name, nutrition_per_100g: item.nutrition_per_100g, conflict_type: i ? "new" : "name_conflict", existing: i ? null : item })),
      dishes: [{ key: "dish-1", name: dishes[0].name, conflict_type: "new", existing_id: null }],
    },
  };
}

export function mutationResponse(path, state) {
  if (path === "/sharing/packages") return { id: "audit-package", type: "ingredients", item_count: 1, deep_link: "https://t.me/example_bot?start=share_AUDIT_NOT_A_REAL_TOKEN", telegram_share_url: "https://t.me/share/url?url=AUDIT", expires_at: "2026-10-01T00:00:00Z" };
  if (path === "/account/deletion-request") return { confirmation_token: "AUDIT_ONLY", confirmation_phrase: "УДАЛИТЬ МОИ ДАННЫЕ", expires_at: "2026-09-13T09:10:00Z" };
  if (path === "/barcodes/lookup") return {
    barcode: "1234567890128", found: state !== "barcode-not-found", name: ["barcode-missing", "barcode-not-found"].includes(state) ? null : ingredients[0].name,
    brand: "Тестовая марка", package_weight_g: "150", package_quantity: "150 г", package_quantity_unit: "g", serving_size: null,
    nutrition_per_100g: ["barcode-missing", "barcode-not-found"].includes(state) ? { energy_kcal: null, protein_g: null, fat_g: null, carbs_g: null } : ingredients[0].nutrition_per_100g,
    photo_url: null, missing_fields: ["barcode-missing", "barcode-not-found"].includes(state) ? ["name", "energy_kcal", "protein_g", "fat_g", "carbs_g", "photo_url"] : ["photo_url"],
    derived_fields: state === "barcode-derived" ? ["energy_kcal"] : [], source: "open_food_facts", source_url: "https://world.openfoodfacts.org/product/1234567890128", confirmation_token: "AUDIT_ONLY_CONFIRMATION_TOKEN",
  };
  return undefined;
}
