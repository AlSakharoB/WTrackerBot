export interface CurrentUser {
  id: string;
  telegram_id: string;
  username: string | null;
  first_name: string | null;
  last_name: string | null;
  language_code: string | null;
  timezone: string;
  app_version: string;
}

export type NumberFormat = "automatic" | "one_decimal" | "two_decimals";
export type AfterFoodAddAction = "open_today" | "stay";

export interface Profile extends CurrentUser {
  photo_url: string | null;
  number_format: NumberFormat;
  after_food_add_action: AfterFoodAddAction;
  confirm_deletions: boolean;
  reminders_enabled: boolean;
}

export type ProfileSettingsUpdate = Partial<
  Pick<
    Profile,
    "timezone" | "number_format" | "after_food_add_action" | "confirm_deletions"
  >
>;

export interface ProfileStats {
  diary_days: number;
  ingredients: number;
  dishes: number;
  diary_entries: number;
  weight_entries: number;
  active_weight_goals: number;
  share_packages: number;
  imported_packages: number;
}

export interface NutritionGoal {
  id: string;
  energy_kcal: string | null;
  protein_g: string | null;
  fat_g: string | null;
  carbs_g: string | null;
  effective_from: string;
  effective_to: string | null;
}

export interface NutritionGoalUpdate {
  enabled: boolean;
  energy_kcal?: string | null;
  protein_g?: string | null;
  fat_g?: string | null;
  carbs_g?: string | null;
  effective_from?: string;
}

export type ReminderType = "weigh_in" | "nutrition";

export interface Reminder {
  id: string;
  type: ReminderType;
  enabled: boolean;
  time_local: string;
  weekdays: number[];
  updated_at: string;
}

export interface ReminderInput {
  type: ReminderType;
  time_local: string;
  weekdays: number[];
}

export type ReminderUpdate = Partial<
  Pick<Reminder, "enabled" | "time_local" | "weekdays">
>;

export interface DeletionChallenge {
  confirmation_token: string;
  confirmation_phrase: string;
  expires_at: string;
}

export interface RationNutrition {
  energy_kcal: string;
  protein_g: string;
  fat_g: string;
  carbs_g: string;
}

export interface RationMacroPercentages {
  protein: number;
  fat: number;
  carbs: number;
}

export interface RationGoal {
  energy_kcal: string | null;
  protein_g: string | null;
  fat_g: string | null;
  carbs_g: string | null;
}

export type MealType = "breakfast" | "lunch" | "dinner" | "snack" | "other";

export interface RationEntry {
  id: string;
  type: "ingredient" | "dish";
  source_id: string | null;
  source_available: boolean;
  source_name: string;
  grams: string;
  meal_type: MealType;
  nutrition: RationNutrition;
  created_at: string;
  updated_at: string;
}

export type RationSourceKind = "all" | "ingredient" | "dish";

export interface RationSource {
  id: string;
  type: "ingredient" | "dish";
  name: string;
  default_grams: string;
  nutrition_per_100g: RationNutrition;
  usage_count: number;
  last_used_at: string | null;
}

export interface RationEntryCreate {
  source_type: "ingredient" | "dish";
  source_id: string;
  grams: string;
  meal_type: MealType;
}

export interface RationEntryUpdate {
  expected_updated_at: string;
  grams?: string;
  meal_type?: MealType;
  entry_date?: string;
}

export interface RationEntryCopy {
  entry_date: string;
  meal_type?: MealType;
}

export interface RationMeal {
  type: MealType;
  label: string;
  totals: RationNutrition;
  entries: RationEntry[];
}

export interface RationSummary {
  date: string;
  timezone: string;
  number_format: NumberFormat;
  is_today: boolean;
  is_future: boolean;
  entry_count: number;
  totals: RationNutrition;
  macro_percentages: RationMacroPercentages;
  goal: RationGoal | null;
}

export interface RationDay extends RationSummary {
  meals: RationMeal[];
}

export interface WeightEntry {
  id: string;
  weight_kg: string;
  measured_at: string;
  note: string | null;
  updated_at: string;
}

export interface WeightChartPoint extends WeightEntry {
  moving_average_7d_kg: string | null;
}

export interface WeightGoalProgress {
  percentage: string;
  completed_kg: string;
  remaining_kg: string;
  achieved: boolean;
}

export interface WeightGoal {
  id: string;
  target_weight_kg: string;
  start_weight_kg: string | null;
  target_date: string | null;
  current_weight_kg: string | null;
  progress: WeightGoalProgress | null;
  updated_at: string;
}

export interface WeightRange {
  timezone: string;
  date_from: string;
  date_to: string;
  current: WeightEntry | null;
  previous: WeightEntry | null;
  change_from_previous_kg: string | null;
  period_change_kg: string | null;
  minimum_kg: string | null;
  maximum_kg: string | null;
  goal: WeightGoal | null;
  points: WeightChartPoint[];
  history: WeightEntry[];
}

export interface WeightEntryCreate {
  weight_kg: string;
  measured_at: string;
  note?: string | null;
}

export interface WeightEntryUpdate {
  expected_updated_at: string;
  weight_kg?: string;
  measured_at?: string;
  note?: string | null;
}

export interface WeightGoalUpdate {
  enabled: boolean;
  target_weight_kg?: string;
  target_date?: string | null;
}

export type FoodKind = "ingredients" | "dishes";
export type FoodSort = "name_asc" | "name_desc" | "newest" | "oldest";

export interface FoodNutrition {
  energy_kcal: string;
  protein_g: string;
  fat_g: string;
  carbs_g: string;
}

export interface Ingredient {
  id: string;
  name: string;
  nutrition_per_100g: FoodNutrition;
  folder_id: string | null;
  package_weight_g: string | null;
  photo_url: string | null;
  source_name: string | null;
  source_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface IngredientInput {
  name: string;
  energy_kcal_per_100g: string;
  protein_g_per_100g: string;
  fat_g_per_100g: string;
  carbs_g_per_100g: string;
  package_weight_g?: string | null;
  photo_url?: string | null;
  source_name?: string | null;
  source_url?: string | null;
  folder_id?: string | null;
}

export interface DishComponent {
  ingredient: Ingredient;
  grams: string;
}

export interface Dish {
  id: string;
  name: string;
  total_weight_g: string;
  nutrition_total: FoodNutrition;
  nutrition_per_100g: FoodNutrition;
  components: DishComponent[];
  folder_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface DishInput {
  name: string;
  components: Array<{ ingredient_id: string; grams: string }>;
  folder_id?: string | null;
}

export interface FoodFolder {
  id: string;
  name: string;
  sort_order: number;
  item_count: number;
  ingredient_count: number;
  dish_count: number;
  created_at: string;
  updated_at: string;
}

export interface BarcodeLookup {
  barcode: string;
  found: boolean;
  name: string | null;
  brand: string | null;
  package_weight_g: string | null;
  package_quantity: string | null;
  package_quantity_unit: string | null;
  serving_size: string | null;
  nutrition_per_100g: {
    energy_kcal: string | null;
    protein_g: string | null;
    fat_g: string | null;
    carbs_g: string | null;
  };
  photo_url: string | null;
  missing_fields: string[];
  derived_fields: string[];
  source: "open_food_facts";
  source_url: string;
  confirmation_token: string;
}

export interface BarcodeIngredientInput extends IngredientInput {
  confirmation_token: string;
  confirmed: true;
}

export interface FoodPageResult<T> {
  items: T[];
  next_cursor: string | null;
}

export interface DeleteConsequence {
  can_delete: boolean;
  message: string;
  dependencies: string[];
}

export interface SharingPackage {
  id: string;
  type: FoodKind;
  item_count: number;
  deep_link: string;
  telegram_share_url: string;
  expires_at: string;
}

export interface SharingIngredientPreview {
  key: string;
  name: string;
  nutrition_per_100g: FoodNutrition;
  conflict_type: "new" | "exact_same" | "name_conflict" | "similar_conflict";
  existing: Ingredient | null;
}

export interface SharingDishPreview {
  key: string;
  name: string;
  conflict_type: "new" | "name_conflict" | "similar_conflict";
  existing_id: string | null;
}

export interface SharingPreview {
  package_id: string;
  type: FoodKind;
  item_count: number;
  is_owner: boolean;
  already_imported: boolean;
  expires_at: string;
  ingredients: SharingIngredientPreview[];
  dishes: SharingDishPreview[];
}

export interface SharingImportResult {
  already_imported: boolean;
  created_ingredients: number;
  created_dishes: number;
}

export type ThemeMode = "system" | "light" | "dark";
export type DefaultSection = "ration" | "food" | "weight" | "profile";

export interface UIPreferences {
  theme_mode: ThemeMode;
  default_section: DefaultSection;
  default_weight_unit: "kg";
  compact_lists: boolean;
  updated_at: string;
}

export type UIPreferencesUpdate = Partial<
  Pick<UIPreferences, "theme_mode" | "default_section" | "compact_lists">
>;

interface ErrorEnvelope {
  error?: {
    message?: string;
    correlation_id?: string;
    details?: Record<string, unknown>;
    field_errors?: Record<string, string>;
  };
}

export class APIError extends Error {
  public constructor(
    message: string,
    public readonly status: number,
    public readonly correlationId?: string,
    public readonly details?: Record<string, unknown>,
    public readonly fieldErrors?: Record<string, string>,
  ) {
    super(message);
  }
}

export async function fetchCurrentUser(initData: string): Promise<CurrentUser> {
  const response = await fetch("/api/v1/me", {
    headers: { Authorization: `tma ${initData}` },
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as ErrorEnvelope;
    throw new APIError(
      payload.error?.message ?? "Не удалось загрузить профиль",
      response.status,
      payload.error?.correlation_id,
      payload.error?.details,
      payload.error?.field_errors,
    );
  }
  return (await response.json()) as CurrentUser;
}

async function parseResponse<T>(response: Response, fallback: string): Promise<T> {
  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as ErrorEnvelope;
    throw new APIError(
      payload.error?.message ?? fallback,
      response.status,
      payload.error?.correlation_id,
      payload.error?.details,
      payload.error?.field_errors,
    );
  }
  return (await response.json()) as T;
}

function authorizationHeaders(initData: string): HeadersInit {
  return { Authorization: `tma ${initData}` };
}

function jsonHeaders(initData: string, idempotencyKey?: string): HeadersInit {
  return {
    ...authorizationHeaders(initData),
    "Content-Type": "application/json",
    ...(idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {}),
  };
}

export async function fetchUIPreferences(initData: string): Promise<UIPreferences> {
  const response = await fetch("/api/v1/ui-preferences", {
    headers: { Authorization: `tma ${initData}` },
  });
  return parseResponse(response, "Не удалось загрузить настройки интерфейса");
}

export async function updateUIPreferences(
  initData: string,
  update: UIPreferencesUpdate,
): Promise<UIPreferences> {
  const response = await fetch("/api/v1/ui-preferences", {
    method: "PATCH",
    headers: {
      Authorization: `tma ${initData}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(update),
  });
  return parseResponse(response, "Не удалось сохранить настройки интерфейса");
}

export async function fetchProfile(initData: string): Promise<Profile> {
  const response = await fetch("/api/v1/profile", {
    headers: authorizationHeaders(initData),
  });
  return parseResponse(response, "Не удалось загрузить профиль");
}

export async function updateProfileSettings(
  initData: string,
  update: ProfileSettingsUpdate,
): Promise<Profile> {
  const response = await fetch("/api/v1/profile/settings", {
    method: "PATCH",
    headers: jsonHeaders(initData),
    body: JSON.stringify(update),
  });
  return parseResponse(response, "Не удалось сохранить настройки рациона");
}

export async function fetchProfileStats(initData: string): Promise<ProfileStats> {
  const response = await fetch("/api/v1/profile/stats", {
    headers: authorizationHeaders(initData),
  });
  return parseResponse(response, "Не удалось загрузить статистику профиля");
}

export async function fetchNutritionGoal(
  initData: string,
): Promise<NutritionGoal | null> {
  const response = await fetch("/api/v1/goals/nutrition", {
    headers: authorizationHeaders(initData),
  });
  return parseResponse(response, "Не удалось загрузить цели питания");
}

export async function updateNutritionGoal(
  initData: string,
  update: NutritionGoalUpdate,
): Promise<NutritionGoal | null> {
  const response = await fetch("/api/v1/goals/nutrition", {
    method: "PUT",
    headers: jsonHeaders(initData),
    body: JSON.stringify(update),
  });
  return parseResponse(response, "Не удалось сохранить цели питания");
}

export async function fetchReminders(initData: string): Promise<Reminder[]> {
  const response = await fetch("/api/v1/reminders", {
    headers: authorizationHeaders(initData),
  });
  return parseResponse(response, "Не удалось загрузить напоминания");
}

export async function createReminder(
  initData: string,
  input: ReminderInput,
  idempotencyKey: string,
): Promise<Reminder> {
  const response = await fetch("/api/v1/reminders", {
    method: "POST",
    headers: jsonHeaders(initData, idempotencyKey),
    body: JSON.stringify(input),
  });
  return parseResponse(response, "Не удалось создать напоминание");
}

export async function updateReminder(
  initData: string,
  id: string,
  update: ReminderUpdate,
): Promise<Reminder> {
  const response = await fetch(`/api/v1/reminders/${id}`, {
    method: "PATCH",
    headers: jsonHeaders(initData),
    body: JSON.stringify(update),
  });
  return parseResponse(response, "Не удалось обновить напоминание");
}

export async function deleteReminder(
  initData: string,
  id: string,
): Promise<void> {
  const response = await fetch(`/api/v1/reminders/${id}`, {
    method: "DELETE",
    headers: authorizationHeaders(initData),
  });
  if (!response.ok) {
    await parseResponse<unknown>(response, "Не удалось удалить напоминание");
  }
}

export async function downloadAccountExport(initData: string): Promise<Blob> {
  const response = await fetch("/api/v1/account/export", {
    headers: authorizationHeaders(initData),
  });
  if (!response.ok) {
    await parseResponse<unknown>(response, "Не удалось подготовить экспорт");
  }
  return response.blob();
}

export async function requestAccountDeletion(
  initData: string,
  idempotencyKey: string,
): Promise<DeletionChallenge> {
  const response = await fetch("/api/v1/account/deletion-request", {
    method: "POST",
    headers: jsonHeaders(initData, idempotencyKey),
    body: "{}",
  });
  return parseResponse(response, "Не удалось начать удаление данных");
}

export async function confirmAccountDeletion(
  initData: string,
  challenge: DeletionChallenge,
  phrase: string,
  idempotencyKey: string,
): Promise<void> {
  const response = await fetch("/api/v1/account/deletion-confirm", {
    method: "POST",
    headers: jsonHeaders(initData, idempotencyKey),
    body: JSON.stringify({
      confirmation_token: challenge.confirmation_token,
      confirmation_phrase: phrase,
    }),
  });
  await parseResponse<unknown>(response, "Не удалось удалить данные");
}

export async function fetchRationDay(
  initData: string,
  date: string,
): Promise<RationDay> {
  const response = await fetch(`/api/v1/ration/${date}`, {
    headers: authorizationHeaders(initData),
  });
  return parseResponse(response, "Не удалось загрузить рацион");
}

export async function fetchRationSummary(
  initData: string,
  date: string,
): Promise<RationSummary> {
  const response = await fetch(`/api/v1/ration/${date}/summary`, {
    headers: authorizationHeaders(initData),
  });
  return parseResponse(response, "Не удалось загрузить итоги рациона");
}

export async function fetchRationSources(
  initData: string,
  query: string,
  kind: RationSourceKind,
): Promise<RationSource[]> {
  const params = new URLSearchParams({ kind, limit: "30" });
  if (query.trim()) params.set("q", query.trim());
  const response = await fetch(`/api/v1/ration/sources?${params}`, {
    headers: authorizationHeaders(initData),
  });
  const payload = await parseResponse<{ items: RationSource[] }>(
    response,
    "Не удалось загрузить продукты",
  );
  return payload.items;
}

export async function createRationEntry(
  initData: string,
  date: string,
  input: RationEntryCreate,
  idempotencyKey: string,
): Promise<RationEntry> {
  const response = await fetch(`/api/v1/ration/${date}/entries`, {
    method: "POST",
    headers: jsonHeaders(initData, idempotencyKey),
    body: JSON.stringify(input),
  });
  return parseResponse(response, "Не удалось добавить запись");
}

export async function updateRationEntry(
  initData: string,
  id: string,
  update: RationEntryUpdate,
): Promise<RationEntry> {
  const response = await fetch(`/api/v1/ration/entries/${id}`, {
    method: "PATCH",
    headers: jsonHeaders(initData),
    body: JSON.stringify(update),
  });
  return parseResponse(response, "Не удалось изменить запись");
}

export async function deleteRationEntry(
  initData: string,
  id: string,
): Promise<void> {
  const response = await fetch(`/api/v1/ration/entries/${id}`, {
    method: "DELETE",
    headers: authorizationHeaders(initData),
  });
  if (!response.ok) {
    await parseResponse<unknown>(response, "Не удалось удалить запись");
  }
}

export async function copyRationEntry(
  initData: string,
  id: string,
  input: RationEntryCopy,
  idempotencyKey: string,
): Promise<RationEntry> {
  const response = await fetch(`/api/v1/ration/entries/${id}/copy`, {
    method: "POST",
    headers: jsonHeaders(initData, idempotencyKey),
    body: JSON.stringify(input),
  });
  return parseResponse(response, "Не удалось скопировать запись");
}

export async function fetchWeightRange(
  initData: string,
  dateFrom: string,
  dateTo: string,
): Promise<WeightRange> {
  const params = new URLSearchParams({ from: dateFrom, to: dateTo });
  const response = await fetch(`/api/v1/weight?${params}`, {
    headers: authorizationHeaders(initData),
  });
  return parseResponse(response, "Не удалось загрузить историю веса");
}

export async function createWeightEntry(
  initData: string,
  input: WeightEntryCreate,
  idempotencyKey: string,
): Promise<WeightEntry> {
  const response = await fetch("/api/v1/weight", {
    method: "POST",
    headers: jsonHeaders(initData, idempotencyKey),
    body: JSON.stringify(input),
  });
  return parseResponse(response, "Не удалось записать вес");
}

export async function updateWeightEntry(
  initData: string,
  id: string,
  update: WeightEntryUpdate,
): Promise<WeightEntry> {
  const response = await fetch(`/api/v1/weight/${id}`, {
    method: "PATCH",
    headers: jsonHeaders(initData),
    body: JSON.stringify(update),
  });
  return parseResponse(response, "Не удалось изменить измерение");
}

export async function deleteWeightEntry(
  initData: string,
  id: string,
): Promise<void> {
  const response = await fetch(`/api/v1/weight/${id}`, {
    method: "DELETE",
    headers: authorizationHeaders(initData),
  });
  if (!response.ok) {
    await parseResponse<unknown>(response, "Не удалось удалить измерение");
  }
}

export async function fetchWeightGoal(initData: string): Promise<WeightGoal | null> {
  const response = await fetch("/api/v1/goals/weight", {
    headers: authorizationHeaders(initData),
  });
  return parseResponse(response, "Не удалось загрузить цель веса");
}

export async function updateWeightGoal(
  initData: string,
  update: WeightGoalUpdate,
): Promise<WeightGoal | null> {
  const response = await fetch("/api/v1/goals/weight", {
    method: "PUT",
    headers: jsonHeaders(initData),
    body: JSON.stringify(update),
  });
  return parseResponse(response, "Не удалось сохранить цель веса");
}

export async function fetchIngredients(
  initData: string,
  query: string,
  sort: FoodSort,
  cursor?: string,
  folderId?: string,
): Promise<FoodPageResult<Ingredient>> {
  const params = new URLSearchParams({ sort });
  if (query.trim()) params.set("query", query.trim());
  if (cursor) params.set("cursor", cursor);
  if (folderId) params.set("folder_id", folderId);
  const response = await fetch(`/api/v1/ingredients?${params}`, {
    headers: authorizationHeaders(initData),
  });
  return parseResponse(response, "Не удалось загрузить ингредиенты");
}

export async function createIngredient(
  initData: string,
  input: IngredientInput,
  idempotencyKey: string,
): Promise<Ingredient> {
  const response = await fetch("/api/v1/ingredients", {
    method: "POST",
    headers: jsonHeaders(initData, idempotencyKey),
    body: JSON.stringify(input),
  });
  return parseResponse(response, "Не удалось создать ингредиент");
}

export async function updateIngredient(
  initData: string,
  id: string,
  input: Partial<IngredientInput>,
): Promise<Ingredient> {
  const response = await fetch(`/api/v1/ingredients/${id}`, {
    method: "PATCH",
    headers: jsonHeaders(initData),
    body: JSON.stringify(input),
  });
  return parseResponse(response, "Не удалось изменить ингредиент");
}

export async function fetchDishes(
  initData: string,
  query: string,
  sort: FoodSort,
  cursor?: string,
  folderId?: string,
): Promise<FoodPageResult<Dish>> {
  const params = new URLSearchParams({ sort });
  if (query.trim()) params.set("query", query.trim());
  if (cursor) params.set("cursor", cursor);
  if (folderId) params.set("folder_id", folderId);
  const response = await fetch(`/api/v1/dishes?${params}`, {
    headers: authorizationHeaders(initData),
  });
  return parseResponse(response, "Не удалось загрузить блюда");
}

export async function createDish(
  initData: string,
  input: DishInput,
  idempotencyKey: string,
): Promise<Dish> {
  const response = await fetch("/api/v1/dishes", {
    method: "POST",
    headers: jsonHeaders(initData, idempotencyKey),
    body: JSON.stringify(input),
  });
  return parseResponse(response, "Не удалось создать блюдо");
}

export async function updateDish(
  initData: string,
  id: string,
  input: DishInput,
): Promise<Dish> {
  const response = await fetch(`/api/v1/dishes/${id}`, {
    method: "PATCH",
    headers: jsonHeaders(initData),
    body: JSON.stringify(input),
  });
  return parseResponse(response, "Не удалось изменить блюдо");
}

export async function fetchDeleteConsequence(
  initData: string,
  kind: FoodKind,
  id: string,
): Promise<DeleteConsequence> {
  const response = await fetch(`/api/v1/${kind}/${id}/delete-consequences`, {
    headers: authorizationHeaders(initData),
  });
  return parseResponse(response, "Не удалось проверить связи");
}

export async function deleteFood(
  initData: string,
  kind: FoodKind,
  id: string,
): Promise<void> {
  const response = await fetch(`/api/v1/${kind}/${id}`, {
    method: "DELETE",
    headers: authorizationHeaders(initData),
  });
  if (!response.ok) await parseResponse(response, "Не удалось удалить запись");
}

export async function fetchFoodFolders(initData: string): Promise<FoodFolder[]> {
  const response = await fetch("/api/v1/food-folders", {
    headers: authorizationHeaders(initData),
  });
  const result = await parseResponse<{ items: FoodFolder[] }>(
    response,
    "Не удалось загрузить папки",
  );
  return result.items;
}

export async function createFoodFolder(
  initData: string,
  name: string,
  idempotencyKey: string,
): Promise<FoodFolder> {
  const response = await fetch("/api/v1/food-folders", {
    method: "POST",
    headers: jsonHeaders(initData, idempotencyKey),
    body: JSON.stringify({ name }),
  });
  return parseResponse(response, "Не удалось создать папку");
}

export async function renameFoodFolder(
  initData: string,
  id: string,
  name: string,
): Promise<FoodFolder> {
  const response = await fetch(`/api/v1/food-folders/${id}`, {
    method: "PATCH",
    headers: jsonHeaders(initData),
    body: JSON.stringify({ name }),
  });
  return parseResponse(response, "Не удалось переименовать папку");
}

export async function deleteFoodFolder(initData: string, id: string): Promise<void> {
  const response = await fetch(`/api/v1/food-folders/${id}`, {
    method: "DELETE",
    headers: authorizationHeaders(initData),
  });
  if (!response.ok) await parseResponse(response, "Не удалось удалить папку");
}

export async function reorderFoodFolders(
  initData: string,
  folderIds: string[],
): Promise<FoodFolder[]> {
  const response = await fetch("/api/v1/food-folders/reorder", {
    method: "POST",
    headers: jsonHeaders(initData),
    body: JSON.stringify({ folder_ids: folderIds }),
  });
  const result = await parseResponse<{ items: FoodFolder[] }>(
    response,
    "Не удалось изменить порядок папок",
  );
  return result.items;
}

export async function moveFoodItems(
  initData: string,
  type: "ingredient" | "dish",
  itemIds: string[],
  folderId: string | null,
): Promise<void> {
  const response = await fetch("/api/v1/food-items/folder-batch", {
    method: "POST",
    headers: jsonHeaders(initData),
    body: JSON.stringify({ type, item_ids: itemIds, folder_id: folderId }),
  });
  await parseResponse(response, "Не удалось переместить позиции");
}

export async function lookupBarcode(
  initData: string,
  barcode: string,
): Promise<BarcodeLookup> {
  const response = await fetch("/api/v1/barcodes/lookup", {
    method: "POST",
    headers: jsonHeaders(initData),
    body: JSON.stringify({ barcode }),
  });
  return parseResponse(response, "Не удалось проверить штрихкод");
}

export async function createBarcodeIngredient(
  initData: string,
  barcode: string,
  input: BarcodeIngredientInput,
  idempotencyKey: string,
): Promise<Ingredient> {
  const response = await fetch(`/api/v1/barcodes/${barcode}/create-ingredient`, {
    method: "POST",
    headers: jsonHeaders(initData, idempotencyKey),
    body: JSON.stringify(input),
  });
  return parseResponse(response, "Не удалось создать ингредиент");
}

export async function createSharingPackage(
  initData: string,
  type: FoodKind,
  itemIds: string[],
  idempotencyKey: string,
): Promise<SharingPackage> {
  const response = await fetch("/api/v1/sharing/packages", {
    method: "POST",
    headers: jsonHeaders(initData, idempotencyKey),
    body: JSON.stringify({ type, item_ids: itemIds }),
  });
  return parseResponse(response, "Не удалось создать ссылку");
}

export async function revokeSharingPackage(
  initData: string,
  id: string,
): Promise<void> {
  const response = await fetch(`/api/v1/sharing/packages/${id}`, {
    method: "DELETE",
    headers: authorizationHeaders(initData),
  });
  if (!response.ok) await parseResponse(response, "Не удалось отозвать ссылку");
}

export async function fetchSharingPreview(
  initData: string,
  token: string,
): Promise<SharingPreview> {
  const response = await fetch(`/api/v1/sharing/packages/${token}/preview`, {
    headers: authorizationHeaders(initData),
  });
  return parseResponse(response, "Не удалось открыть пакет");
}

export async function importSharingPackage(
  initData: string,
  token: string,
  preview: SharingPreview,
): Promise<SharingImportResult> {
  const ingredientDecisions = Object.fromEntries(
    preview.ingredients
      .filter((item) => item.conflict_type === "name_conflict" || item.conflict_type === "similar_conflict")
      .map((item) => [item.key, "reuse"]),
  );
  const dishDecisions = Object.fromEntries(
    preview.dishes
      .filter((item) => item.conflict_type !== "new")
      .map((item) => [item.key, "create_copy"]),
  );
  const response = await fetch(`/api/v1/sharing/packages/${token}/import`, {
    method: "POST",
    headers: jsonHeaders(initData),
    body: JSON.stringify({
      ingredient_decisions: ingredientDecisions,
      dish_decisions: dishDecisions,
    }),
  });
  return parseResponse(response, "Не удалось импортировать пакет");
}
