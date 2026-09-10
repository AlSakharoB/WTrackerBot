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
  error?: { message?: string; correlation_id?: string };
}

export class APIError extends Error {
  public constructor(
    message: string,
    public readonly status: number,
    public readonly correlationId?: string,
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
