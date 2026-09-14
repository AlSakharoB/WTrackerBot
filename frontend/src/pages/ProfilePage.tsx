import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bell,
  CalendarDays,
  Check,
  ChevronRight,
  Clock3,
  Database,
  Download,
  FileJson,
  Info,
  LayoutPanelTop,
  Moon,
  Salad,
  Scale,
  Settings2,
  ShieldCheck,
  Trash2,
  UserRound,
  Utensils,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

import {
  APIError,
  confirmAccountDeletion,
  createReminder,
  deleteReminder,
  downloadAccountExport,
  fetchNutritionGoal,
  fetchProfileStats,
  fetchReminders,
  requestAccountDeletion,
  updateNutritionGoal,
  updateReminder,
  type AfterFoodAddAction,
  type DefaultSection,
  type DeletionChallenge,
  type NumberFormat,
  type NutritionGoal,
  type ProfileSettingsUpdate,
  type ProfileStats,
  type Reminder,
  type ReminderType,
  type ThemeMode,
  type UIPreferencesUpdate,
} from "../api/client";
import { useMiniAppContext } from "../app/context";
import {
  BottomSheet,
  ConfirmDialog,
  ErrorState,
  FormField,
  ProductState,
  SegmentedControl,
  Skeleton,
  useToast,
} from "../components/ui";

const THEME_OPTIONS = [
  { value: "system", label: "Системная" },
  { value: "light", label: "Светлая" },
  { value: "dark", label: "Темная" },
] as const;
const NUMBER_OPTIONS = [
  { value: "automatic", label: "Авто" },
  { value: "one_decimal", label: "1 знак" },
  { value: "two_decimals", label: "2 знака" },
] as const;
const AFTER_ADD_OPTIONS = [
  { value: "open_today", label: "Открыть рацион" },
  { value: "stay", label: "Добавить еще" },
] as const;
const SECTION_OPTIONS: Array<{ value: DefaultSection; label: string }> = [
  { value: "ration", label: "Рацион" },
  { value: "food", label: "Еда" },
  { value: "weight", label: "Вес" },
  { value: "profile", label: "Профиль" },
];
const WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
const TIMEZONES = [
  "Europe/Moscow",
  "Europe/Berlin",
  "Europe/London",
  "Asia/Dubai",
  "Asia/Almaty",
  "Asia/Tbilisi",
  "Europe/Minsk",
  "Asia/Tashkent",
  "Asia/Yekaterinburg",
  "Asia/Novosibirsk",
  "Asia/Vladivostok",
  "UTC",
];
const EMPTY_STATS: ProfileStats = {
  diary_days: 0,
  ingredients: 0,
  dishes: 0,
  diary_entries: 0,
  weight_entries: 0,
  active_weight_goals: 0,
  share_packages: 0,
  imported_packages: 0,
};

type ProfileEditor =
  | "goal"
  | "theme"
  | "section"
  | "number"
  | "timezone"
  | "after-add"
  | "reminder-weigh_in"
  | "reminder-nutrition"
  | null;

interface GoalDraft {
  energy_kcal: string;
  protein_g: string;
  fat_g: string;
  carbs_g: string;
}

interface SettingRowProps {
  icon: typeof Settings2;
  label: string;
  value: string;
  pending?: boolean;
  onClick: () => void;
}

function SettingRow({ icon: Icon, label, value, pending = false, onClick }: SettingRowProps) {
  return (
    <button type="button" className="profile-setting-row" disabled={pending} onClick={onClick}>
      <span className="profile-setting-row__icon"><Icon aria-hidden="true" /></span>
      <span><strong>{label}</strong><small>{pending ? "Сохраняем..." : value}</small></span>
      <ChevronRight aria-hidden="true" />
    </button>
  );
}

function SwitchRow({
  label,
  description,
  checked,
  pending,
  onChange,
}: {
  label: string;
  description: string;
  checked: boolean;
  pending: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="profile-switch-row">
      <span><strong>{label}</strong><small>{pending ? "Сохраняем..." : description}</small></span>
      <input type="checkbox" checked={checked} disabled={pending} onChange={(event) => onChange(event.target.checked)} />
    </label>
  );
}

function errorDetails(error: unknown): ReactNode {
  if (!(error instanceof Error)) return null;
  return (
    <p className="form-error profile-form-error" role="alert">
      <span>{error.message}</span>
      {error instanceof APIError && error.correlationId && <small>Correlation ID: {error.correlationId}</small>}
    </p>
  );
}

function weekdaysLabel(weekdays: number[]): string {
  if (weekdays.length === 7) return "Каждый день";
  if (weekdays.length === 0) return "Дни не выбраны";
  return weekdays.map((weekday) => WEEKDAYS[weekday]).filter(Boolean).join(", ");
}

function goalDraftFrom(goal: NutritionGoal | null | undefined): GoalDraft {
  return {
    energy_kcal: goal?.energy_kcal ?? "",
    protein_g: goal?.protein_g ?? "",
    fat_g: goal?.fat_g ?? "",
    carbs_g: goal?.carbs_g ?? "",
  };
}

function mutationKey(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
}

function ReminderEditor({
  type,
  reminder,
  pending,
  error,
  onSave,
  onDelete,
}: {
  type: ReminderType;
  reminder?: Reminder;
  pending: boolean;
  error: unknown;
  onSave: (type: ReminderType, time: string, weekdays: number[]) => Promise<void>;
  onDelete: (reminder: Reminder) => void;
}) {
  const [time, setTime] = useState(reminder?.time_local ?? (type === "weigh_in" ? "8:00" : "20:00"));
  const [weekdays, setWeekdays] = useState<number[]>(reminder?.weekdays ?? [0, 1, 2, 3, 4, 5, 6]);
  const isWeighIn = type === "weigh_in";
  const toggleWeekday = (weekday: number) => {
    setWeekdays((current) => current.includes(weekday)
      ? current.filter((item) => item !== weekday)
      : [...current, weekday].sort());
  };

  return (
    <form className="reminder-editor" onSubmit={(event) => { event.preventDefault(); void onSave(type, time, weekdays); }}>
      <div className="reminder-editor__heading">
        <span className="reminder-editor__icon">{isWeighIn ? <Scale aria-hidden="true" /> : <Salad aria-hidden="true" />}</span>
        <div><strong>{isWeighIn ? "Взвешивание" : "Проверка рациона"}</strong><small>{isWeighIn ? "Если вес еще не записан" : "Сводка по дневному рациону"}</small></div>
      </div>
      <FormField label="Время" htmlFor={`reminder-time-${type}`} hint="Можно вводить 8:00 или 08:00">
        <input id={`reminder-time-${type}`} inputMode="numeric" value={time} placeholder="8:00" onChange={(event) => setTime(event.target.value)} />
      </FormField>
      <fieldset className="weekday-fieldset">
        <legend>Дни недели</legend>
        <div className="weekday-picker">
          {WEEKDAYS.map((label, index) => <button key={label} type="button" className={weekdays.includes(index) ? "is-active" : ""} aria-pressed={weekdays.includes(index)} onClick={() => toggleWeekday(index)}>{label}</button>)}
        </div>
      </fieldset>
      {errorDetails(error)}
      <div className="sheet-actions">
        {reminder && <button type="button" className="button-text button-text--danger" disabled={pending} onClick={() => onDelete(reminder)}><Trash2 aria-hidden="true" size={17} />Удалить</button>}
        <button type="submit" className="button-primary button-with-icon" disabled={pending || weekdays.length === 0 || time.trim().length < 4}><Check aria-hidden="true" size={18} />{pending ? "Сохраняем..." : reminder ? "Сохранить" : "Создать"}</button>
      </div>
    </form>
  );
}

export function ProfilePage() {
  const {
    profile,
    initData,
    preferences,
    isDevelopmentPreview,
    preferencesPending,
    profilePending,
    updatePreferences,
    updateProfile,
    closeMiniApp,
  } = useMiniAppContext();
  const authorized = initData.length > 0;
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [previewGoal, setPreviewGoal] = useState<NutritionGoal | null>(null);
  const [previewReminders, setPreviewReminders] = useState<Reminder[]>([]);
  const [editor, setEditor] = useState<ProfileEditor>(null);
  const [editorError, setEditorError] = useState<unknown>(null);
  const [goalDraft, setGoalDraft] = useState<GoalDraft>(() => goalDraftFrom(null));
  const [timezoneDraft, setTimezoneDraft] = useState(profile.timezone);
  const [deleteWarningOpen, setDeleteWarningOpen] = useState(false);
  const [reminderToDelete, setReminderToDelete] = useState<Reminder | null>(null);
  const [deletionChallenge, setDeletionChallenge] = useState<DeletionChallenge | null>(null);
  const [deletionPhrase, setDeletionPhrase] = useState("");
  const [accountDeleted, setAccountDeleted] = useState(false);

  const statsQuery = useQuery({ queryKey: ["profile-stats"], queryFn: () => fetchProfileStats(initData), enabled: authorized, retry: false });
  const goalQuery = useQuery({ queryKey: ["nutrition-goal"], queryFn: () => fetchNutritionGoal(initData), enabled: authorized, retry: false });
  const remindersQuery = useQuery({ queryKey: ["reminders"], queryFn: () => fetchReminders(initData), enabled: authorized, retry: false });
  const goalMutation = useMutation({
    mutationFn: (draft: GoalDraft | null) => updateNutritionGoal(initData, draft ? {
      enabled: true,
      energy_kcal: draft.energy_kcal.trim() || null,
      protein_g: draft.protein_g.trim() || null,
      fat_g: draft.fat_g.trim() || null,
      carbs_g: draft.carbs_g.trim() || null,
    } : { enabled: false }),
  });
  const reminderMutation = useMutation({
    mutationFn: async ({ type, time, weekdays }: { type: ReminderType; time: string; weekdays: number[] }) => {
      const existing = (remindersQuery.data ?? []).find((item) => item.type === type);
      return existing
        ? updateReminder(initData, existing.id, { time_local: time, weekdays })
        : createReminder(initData, { type, time_local: time, weekdays }, mutationKey());
    },
  });
  const toggleReminderMutation = useMutation({ mutationFn: ({ reminder, enabled }: { reminder: Reminder; enabled: boolean }) => updateReminder(initData, reminder.id, { enabled }) });
  const removeReminderMutation = useMutation({ mutationFn: (reminder: Reminder) => deleteReminder(initData, reminder.id) });
  const exportMutation = useMutation({ mutationFn: () => downloadAccountExport(initData) });
  const deletionRequestMutation = useMutation({ mutationFn: () => requestAccountDeletion(initData, mutationKey()) });
  const deletionConfirmMutation = useMutation({ mutationFn: ({ challenge, phrase }: { challenge: DeletionChallenge; phrase: string }) => confirmAccountDeletion(initData, challenge, phrase, mutationKey()) });

  const stats = authorized ? (statsQuery.data ?? EMPTY_STATS) : EMPTY_STATS;
  const goal = authorized ? goalQuery.data : previewGoal;
  const reminders = authorized ? (remindersQuery.data ?? []) : previewReminders;
  const reminderPending = reminderMutation.isPending || toggleReminderMutation.isPending || removeReminderMutation.isPending;
  const loading = authorized && [statsQuery, goalQuery, remindersQuery].some((query) => query.isPending);
  const failed = [statsQuery, goalQuery, remindersQuery].find((query) => query.error)?.error;

  useEffect(() => {
    if (!deletionChallenge) return;
    const delay = new Date(deletionChallenge.expires_at).getTime() - Date.now();
    const expire = () => {
      setDeletionChallenge(null);
      setDeletionPhrase("");
      setEditorError(new Error("Срок подтверждения истек. Начните удаление заново."));
      setDeleteWarningOpen(true);
    };
    const timeout = window.setTimeout(expire, Math.max(0, delay));
    return () => window.clearTimeout(timeout);
  }, [deletionChallenge]);

  const openEditor = (next: ProfileEditor) => {
    setEditorError(null);
    if (next === "goal") setGoalDraft(goalDraftFrom(goal));
    if (next === "timezone") setTimezoneDraft(profile.timezone);
    setEditor(next);
  };
  const closeEditor = () => {
    if (preferencesPending || profilePending || goalMutation.isPending || reminderPending) return;
    setEditor(null);
    setEditorError(null);
  };
  const savePreferences = async (update: UIPreferencesUpdate) => {
    setEditorError(null);
    try {
      await updatePreferences(update);
      showToast("Настройки сохранены");
      setEditor(null);
    } catch (error) {
      setEditorError(error);
    }
  };
  const saveProfile = async (update: ProfileSettingsUpdate, close = true) => {
    setEditorError(null);
    try {
      await updateProfile(update);
      if (update.timezone || update.number_format) {
        await queryClient.invalidateQueries({ queryKey: ["ration"] });
        await queryClient.invalidateQueries({ queryKey: ["weight"] });
      }
      showToast("Настройки сохранены");
      if (close) setEditor(null);
    } catch (error) {
      setEditorError(error);
    }
  };
  const saveGoal = async () => {
    setEditorError(null);
    try {
      if (authorized) {
        const saved = await goalMutation.mutateAsync(goalDraft);
        queryClient.setQueryData(["nutrition-goal"], saved);
      } else {
        setPreviewGoal({ id: "preview", ...goalDraft, effective_from: new Date().toISOString().slice(0, 10), effective_to: null });
      }
      await queryClient.invalidateQueries({ queryKey: ["profile"] });
      await queryClient.invalidateQueries({ queryKey: ["ration"] });
      showToast("Цели питания сохранены");
      setEditor(null);
    } catch (error) {
      setEditorError(error);
    }
  };
  const disableGoal = async () => {
    setEditorError(null);
    try {
      if (authorized) {
        const saved = await goalMutation.mutateAsync(null);
        queryClient.setQueryData(["nutrition-goal"], saved);
      } else setPreviewGoal(null);
      await queryClient.invalidateQueries({ queryKey: ["profile"] });
      await queryClient.invalidateQueries({ queryKey: ["ration"] });
      showToast("Цели питания отключены");
      setEditor(null);
    } catch (error) {
      setEditorError(error);
    }
  };
  const refreshReminders = async () => {
    await queryClient.invalidateQueries({ queryKey: ["reminders"] });
    await queryClient.invalidateQueries({ queryKey: ["profile"] });
  };
  const saveReminder = async (type: ReminderType, time: string, weekdays: number[]) => {
    setEditorError(null);
    try {
      if (authorized) {
        await reminderMutation.mutateAsync({ type, time, weekdays });
        await refreshReminders();
      } else {
        setPreviewReminders((current) => {
          const item: Reminder = { id: current.find((candidate) => candidate.type === type)?.id ?? type, type, enabled: true, time_local: time.length === 4 ? `0${time}` : time, weekdays, updated_at: new Date().toISOString() };
          return [...current.filter((candidate) => candidate.type !== type), item];
        });
      }
      showToast("Напоминание сохранено");
      setEditor(null);
    } catch (error) {
      setEditorError(error);
    }
  };
  const toggleReminder = async (reminder: Reminder, enabled: boolean) => {
    setEditorError(null);
    try {
      if (authorized) {
        await toggleReminderMutation.mutateAsync({ reminder, enabled });
        await refreshReminders();
      } else setPreviewReminders((current) => current.map((item) => item.id === reminder.id ? { ...item, enabled } : item));
      showToast(enabled ? "Напоминание включено" : "Напоминание выключено");
    } catch (error) {
      setEditorError(error);
    }
  };
  const removeReminder = async () => {
    if (!reminderToDelete) return;
    setEditorError(null);
    try {
      if (authorized) {
        await removeReminderMutation.mutateAsync(reminderToDelete);
        await refreshReminders();
      } else setPreviewReminders((current) => current.filter((item) => item.id !== reminderToDelete.id));
      setReminderToDelete(null);
      setEditor(null);
      showToast("Напоминание удалено");
    } catch (error) {
      setReminderToDelete(null);
      setEditorError(error);
    }
  };
  const exportData = async () => {
    if (!authorized) {
      setEditorError(new Error("Экспорт доступен после открытия через Telegram"));
      return;
    }
    setEditorError(null);
    try {
      const blob = await exportMutation.mutateAsync();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "wtrackerbot-data.json";
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      showToast("Экспорт подготовлен");
    } catch (error) {
      setEditorError(error);
    }
  };
  const beginDeletion = async () => {
    if (deletionRequestMutation.isPending) return;
    if (!authorized) {
      setDeleteWarningOpen(false);
      setEditorError(new Error("Удаление доступно после открытия через Telegram"));
      return;
    }
    setEditorError(null);
    try {
      const challenge = await deletionRequestMutation.mutateAsync();
      setDeleteWarningOpen(false);
      setDeletionChallenge(challenge);
      setDeletionPhrase("");
    } catch (error) {
      setEditorError(error);
    }
  };
  const confirmDeletion = async () => {
    if (!deletionChallenge) return;
    if (new Date(deletionChallenge.expires_at).getTime() <= Date.now()) {
      setDeletionChallenge(null);
      setDeletionPhrase("");
      setEditorError(new Error("Срок подтверждения истек. Начните удаление заново."));
      setDeleteWarningOpen(true);
      return;
    }
    setEditorError(null);
    try {
      await deletionConfirmMutation.mutateAsync({ challenge: deletionChallenge, phrase: deletionPhrase });
      setDeletionChallenge(null);
      setDeletionPhrase("");
      queryClient.clear();
      setAccountDeleted(true);
    } catch (error) {
      setEditorError(error);
    }
  };

  if (accountDeleted) {
    return <ProductState contained tone="success" icon={Check} title="Данные удалены" message="Рацион, каталог, вес, цели, напоминания и настройки удалены. Теперь Mini App можно закрыть." action={<button type="button" className="button-primary" onClick={closeMiniApp}>Закрыть приложение</button>} />;
  }
  if (loading) return <div className="page page--profile"><div className="profile-loading"><Skeleton lines={5} /></div></div>;
  if (authorized && failed) {
    const failedMessage = failed instanceof APIError && failed.correlationId
      ? `${failed.message} (Correlation ID: ${failed.correlationId})`
      : failed instanceof Error ? failed.message : "Произошла ошибка";
    return <div className="page page--profile"><ErrorState title="Не удалось загрузить профиль" message={failedMessage} onRetry={() => { void statsQuery.refetch(); void goalQuery.refetch(); void remindersQuery.refetch(); }} /></div>;
  }

  const name = [profile.first_name, profile.last_name].filter(Boolean).join(" ");
  const remindersEnabled = reminders.some((item) => item.enabled);
  const sectionLabel = SECTION_OPTIONS.find((option) => option.value === preferences.default_section)?.label ?? "Рацион";
  const numberLabel = NUMBER_OPTIONS.find((option) => option.value === profile.number_format)?.label ?? "Авто";
  const afterAddLabel = profile.after_food_add_action === "stay" ? "Оставаться в добавлении" : "Открывать сегодняшний рацион";
  const goalConfigured = Boolean(goal && [goal.energy_kcal, goal.protein_g, goal.fat_g, goal.carbs_g].some((value) => value !== null));
  const currentReminderType = editor?.startsWith("reminder-") ? editor.replace("reminder-", "") as ReminderType : null;
  const currentReminder = currentReminderType ? reminders.find((item) => item.type === currentReminderType) : undefined;

  return (
    <div className="page page--profile">
      <div className="profile-layout">
        <div className="profile-primary-column">
          <section className="profile-summary" aria-labelledby="profile-name">
            <span className="profile-avatar">{profile.photo_url ? <img src={profile.photo_url} alt="" /> : <UserRound aria-hidden="true" />}</span>
            <div className="profile-identity"><span>Профиль</span><h1 id="profile-name">{name || profile.username || "Пользователь"}</h1><p>{profile.username ? `@${profile.username}` : isDevelopmentPreview ? "Режим разработки" : `Telegram ID ${profile.telegram_id}`}</p></div>
            <span className={`status-badge ${remindersEnabled ? "is-enabled" : ""}`}>{remindersEnabled ? "Напоминания вкл." : "Напоминания выкл."}</span>
          </section>

          <section className="profile-stats" aria-label="Статистика профиля">
            <div><CalendarDays aria-hidden="true" /><strong>{stats.diary_days}</strong><span>дней</span></div>
            <div><Salad aria-hidden="true" /><strong>{stats.ingredients}</strong><span>ингредиентов</span></div>
            <div><Utensils aria-hidden="true" /><strong>{stats.dishes}</strong><span>блюд</span></div>
            <div><Scale aria-hidden="true" /><strong>{stats.weight_entries}</strong><span>измерений</span></div>
          </section>

          <section className="profile-section profile-goals" aria-labelledby="goals-title">
            <header><div><span>Питание</span><h2 id="goals-title">Цели КБЖУ</h2></div><button type="button" className="button-text" onClick={() => openEditor("goal")}>{goalConfigured ? "Изменить" : "Настроить"}</button></header>
            {goalConfigured ? (
              <div className="profile-goal-grid">
                <div><span>Ккал</span><strong>{goal?.energy_kcal ?? "—"}</strong></div>
                <div><span>Белки</span><strong>{goal?.protein_g ? `${goal.protein_g} г` : "—"}</strong></div>
                <div><span>Жиры</span><strong>{goal?.fat_g ? `${goal.fat_g} г` : "—"}</strong></div>
                <div><span>Углеводы</span><strong>{goal?.carbs_g ? `${goal.carbs_g} г` : "—"}</strong></div>
              </div>
            ) : <p className="profile-section-empty">Цели не настроены. Фактические КБЖУ в рационе все равно отображаются.</p>}
          </section>
        </div>

        <div className="profile-settings-column">
          <section className="profile-section" aria-labelledby="interface-title">
            <div className="profile-section-title"><Moon aria-hidden="true" /><div><span>Интерфейс</span><h2 id="interface-title">Внешний вид</h2></div></div>
            <div className="profile-settings-list">
              <SettingRow icon={Moon} label="Тема" value={THEME_OPTIONS.find((option) => option.value === preferences.theme_mode)?.label ?? "Системная"} pending={preferencesPending && editor === "theme"} onClick={() => openEditor("theme")} />
              <SettingRow icon={LayoutPanelTop} label="Начальный раздел" value={sectionLabel} pending={preferencesPending && editor === "section"} onClick={() => openEditor("section")} />
              <SettingRow icon={Settings2} label="Отображение чисел" value={numberLabel} pending={profilePending && editor === "number"} onClick={() => openEditor("number")} />
              <SettingRow icon={Clock3} label="Часовой пояс" value={profile.timezone} pending={profilePending && editor === "timezone"} onClick={() => openEditor("timezone")} />
              <SettingRow icon={Scale} label="Единицы веса" value="Килограммы (кг)" onClick={() => showToast("Сейчас поддерживаются килограммы")} />
              <SwitchRow label="Компактные списки" description="Больше записей помещается на экране" checked={preferences.compact_lists} pending={preferencesPending} onChange={(checked) => void savePreferences({ compact_lists: checked })} />
            </div>
          </section>

          <section className="profile-section" aria-labelledby="behavior-title">
            <div className="profile-section-title"><Settings2 aria-hidden="true" /><div><span>Поведение</span><h2 id="behavior-title">Действия</h2></div></div>
            <div className="profile-settings-list">
              <SettingRow icon={Salad} label="После добавления еды" value={afterAddLabel} pending={profilePending && editor === "after-add"} onClick={() => openEditor("after-add")} />
              <SwitchRow label="Подтверждать удаление" description="Спрашивать перед удалением записей" checked={profile.confirm_deletions} pending={profilePending} onChange={(checked) => void saveProfile({ confirm_deletions: checked }, false)} />
            </div>
          </section>

          <section className="profile-section" aria-labelledby="reminders-title">
            <div className="profile-section-title"><Bell aria-hidden="true" /><div><span>По местному времени</span><h2 id="reminders-title">Напоминания</h2></div></div>
            <div className="profile-settings-list">
              {(["weigh_in", "nutrition"] as ReminderType[]).map((type) => {
                const reminder = reminders.find((item) => item.type === type);
                return (
                  <div className="profile-reminder-row" key={type}>
                    <button type="button" onClick={() => openEditor(`reminder-${type}`)}>
                      <span><strong>{type === "weigh_in" ? "Взвешивание" : "Проверка рациона"}</strong><small>{reminder ? `${reminder.time_local} · ${weekdaysLabel(reminder.weekdays)}` : "Не настроено"}</small></span>
                      <ChevronRight aria-hidden="true" />
                    </button>
                    {reminder && <label title={reminder.enabled ? "Выключить" : "Включить"}><span className="sr-only">{reminder.enabled ? "Выключить" : "Включить"} напоминание</span><input type="checkbox" checked={reminder.enabled} disabled={reminderPending} onChange={(event) => void toggleReminder(reminder, event.target.checked)} /></label>}
                  </div>
                );
              })}
            </div>
            {Boolean(editorError) && !editor && errorDetails(editorError)}
          </section>
        </div>
      </div>

      <section className="profile-section profile-data-section" aria-labelledby="privacy-title">
        <div className="profile-section-title"><ShieldCheck aria-hidden="true" /><div><span>Управление аккаунтом</span><h2 id="privacy-title">Данные и приватность</h2></div></div>
        <div className="data-summary"><Database aria-hidden="true" /><p>{stats.diary_entries} записей рациона, {stats.weight_entries} измерений веса, {stats.share_packages} пакетов обмена и {stats.imported_packages} импортов.</p></div>
        <div className="action-list">
          <button type="button" className="action-row" disabled={exportMutation.isPending} onClick={() => void exportData()}><FileJson aria-hidden="true" /><span><strong>{exportMutation.isPending ? "Готовим экспорт..." : exportMutation.isError ? "Повторить экспорт" : "Скачать мои данные"}</strong><small>JSON-файл со всеми данными аккаунта</small></span><Download aria-hidden="true" /></button>
          <Link className="action-row" to="/privacy-policy"><Info aria-hidden="true" /><span><strong>Политика конфиденциальности</strong><small>Какие данные хранит приложение</small></span><ChevronRight aria-hidden="true" /></Link>
        </div>
        {exportMutation.error && errorDetails(editorError ?? exportMutation.error)}
        <div className="profile-version"><span>WTrackerBot Mini App</span><strong>Версия {profile.app_version}</strong><small>{profile.timezone}</small></div>
      </section>

      <section className="profile-danger-zone" aria-labelledby="danger-title">
        <div><span>Необратимое действие</span><h2 id="danger-title">Удалить все данные</h2><p>Будут удалены рацион, продукты, вес, цели, напоминания и настройки.</p></div>
        <button type="button" className="button-text button-text--danger" onClick={() => { setEditorError(null); setDeleteWarningOpen(true); }}><Trash2 aria-hidden="true" size={18} />Начать удаление</button>
      </section>

      <BottomSheet open={editor === "goal"} title="Цели питания" onClose={closeEditor}>
        <form className="profile-editor-form" onSubmit={(event) => { event.preventDefault(); void saveGoal(); }}>
          <p className="profile-editor-note">Можно заполнить только нужные цели. Даже без целей рацион продолжит показывать фактические граммы БЖУ.</p>
          <div className="goal-grid">
            <FormField label="Калории" htmlFor="goal-energy"><input id="goal-energy" inputMode="decimal" placeholder="2000" value={goalDraft.energy_kcal} onChange={(event) => setGoalDraft({ ...goalDraft, energy_kcal: event.target.value })} /></FormField>
            <FormField label="Белки, г" htmlFor="goal-protein"><input id="goal-protein" inputMode="decimal" placeholder="120" value={goalDraft.protein_g} onChange={(event) => setGoalDraft({ ...goalDraft, protein_g: event.target.value })} /></FormField>
            <FormField label="Жиры, г" htmlFor="goal-fat"><input id="goal-fat" inputMode="decimal" placeholder="70" value={goalDraft.fat_g} onChange={(event) => setGoalDraft({ ...goalDraft, fat_g: event.target.value })} /></FormField>
            <FormField label="Углеводы, г" htmlFor="goal-carbs"><input id="goal-carbs" inputMode="decimal" placeholder="250" value={goalDraft.carbs_g} onChange={(event) => setGoalDraft({ ...goalDraft, carbs_g: event.target.value })} /></FormField>
          </div>
          {errorDetails(editorError)}
          <div className="sheet-actions">{goal && <button type="button" className="button-text" disabled={goalMutation.isPending} onClick={() => void disableGoal()}>Отключить цели</button>}<button type="submit" className="button-primary" disabled={goalMutation.isPending || Object.values(goalDraft).every((value) => !value.trim())}>{goalMutation.isPending ? "Сохраняем..." : "Сохранить"}</button></div>
        </form>
      </BottomSheet>
      <BottomSheet open={editor === "theme"} title="Тема приложения" onClose={closeEditor}><div className="profile-editor-form"><SegmentedControl label="Тема приложения" options={THEME_OPTIONS} value={preferences.theme_mode} onChange={(value: ThemeMode) => void savePreferences({ theme_mode: value })} />{errorDetails(editorError)}</div></BottomSheet>
      <BottomSheet open={editor === "section"} title="Начальный раздел" onClose={closeEditor}><div className="profile-editor-form"><div className="profile-choice-list">{SECTION_OPTIONS.map((option) => <button key={option.value} type="button" className={preferences.default_section === option.value ? "is-active" : ""} aria-pressed={preferences.default_section === option.value} disabled={preferencesPending} onClick={() => void savePreferences({ default_section: option.value })}><span>{option.label}</span><Check aria-hidden="true" /></button>)}</div>{errorDetails(editorError)}</div></BottomSheet>
      <BottomSheet open={editor === "number"} title="Отображение чисел" onClose={closeEditor}><div className="profile-editor-form"><SegmentedControl label="Количество знаков после запятой" options={NUMBER_OPTIONS} value={profile.number_format} onChange={(value: NumberFormat) => void saveProfile({ number_format: value })} />{errorDetails(editorError)}</div></BottomSheet>
      <BottomSheet open={editor === "timezone"} title="Часовой пояс" onClose={closeEditor}><form className="profile-editor-form" onSubmit={(event) => { event.preventDefault(); void saveProfile({ timezone: timezoneDraft }); }}><FormField label="Часовой пояс" htmlFor="timezone" hint="Используется для дат и напоминаний"><select id="timezone" value={timezoneDraft} disabled={profilePending} onChange={(event) => setTimezoneDraft(event.target.value)}>{!TIMEZONES.includes(timezoneDraft) && <option value={timezoneDraft}>{timezoneDraft}</option>}{TIMEZONES.map((timezone) => <option key={timezone} value={timezone}>{timezone}</option>)}</select></FormField>{errorDetails(editorError)}<div className="sheet-actions"><button type="submit" className="button-primary" disabled={profilePending || timezoneDraft === profile.timezone}>{profilePending ? "Сохраняем..." : "Сохранить"}</button></div></form></BottomSheet>
      <BottomSheet open={editor === "after-add"} title="После добавления еды" onClose={closeEditor}><div className="profile-editor-form"><p className="profile-editor-note">Выберите, что показывать после сохранения записи в рационе.</p><SegmentedControl label="Действие после добавления еды" options={AFTER_ADD_OPTIONS} value={profile.after_food_add_action} onChange={(value: AfterFoodAddAction) => void saveProfile({ after_food_add_action: value })} />{errorDetails(editorError)}</div></BottomSheet>
      <BottomSheet open={currentReminderType !== null} title={currentReminderType === "weigh_in" ? "Напоминание о взвешивании" : "Напоминание о рационе"} onClose={closeEditor}>{currentReminderType && <ReminderEditor key={`${currentReminderType}:${currentReminder?.updated_at ?? "new"}`} type={currentReminderType} reminder={currentReminder} pending={reminderPending} error={editorError} onSave={saveReminder} onDelete={setReminderToDelete} />}</BottomSheet>

      <ConfirmDialog open={reminderToDelete !== null} title="Удалить напоминание?" description="Оно перестанет приходить в выбранные дни. Позже его можно создать заново." confirmLabel={removeReminderMutation.isPending ? "Удаляем..." : "Удалить"} destructive onClose={() => setReminderToDelete(null)} onConfirm={() => void removeReminder()} />
      <ConfirmDialog open={deleteWarningOpen} title="Удалить все данные?" description="Будут безвозвратно удалены рацион, ингредиенты, блюда, измерения веса, цели, напоминания и настройки. На следующем шаге потребуется ввести контрольную фразу." confirmLabel={deletionRequestMutation.isPending ? "Подготовка..." : "Продолжить"} destructive onClose={() => setDeleteWarningOpen(false)} onConfirm={() => void beginDeletion()} />
      <BottomSheet open={deletionChallenge !== null} title="Подтверждение удаления" onClose={() => { if (!deletionConfirmMutation.isPending) setDeletionChallenge(null); }}>
        {deletionChallenge && <div className="deletion-confirmation"><p>Введите точную фразу <strong>{deletionChallenge.confirmation_phrase}</strong>.</p><p className="deletion-expiry">Подтверждение действует до {new Intl.DateTimeFormat("ru-RU", { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(new Date(deletionChallenge.expires_at))}.</p><FormField label="Контрольная фраза" htmlFor="deletion-phrase"><input id="deletion-phrase" autoComplete="off" value={deletionPhrase} onChange={(event) => setDeletionPhrase(event.target.value)} /></FormField>{errorDetails(editorError)}<button type="button" className="button-danger button-with-icon" disabled={deletionConfirmMutation.isPending || deletionPhrase !== deletionChallenge.confirmation_phrase} onClick={() => void confirmDeletion()}><Trash2 aria-hidden="true" size={18} />{deletionConfirmMutation.isPending ? "Удаляем..." : "Удалить навсегда"}</button></div>}
      </BottomSheet>
    </div>
  );
}
