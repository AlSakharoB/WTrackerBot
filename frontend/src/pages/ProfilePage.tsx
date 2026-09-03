import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bell,
  CalendarDays,
  Check,
  ChevronRight,
  Clock3,
  Database,
  Download,
  Goal,
  Info,
  Moon,
  Salad,
  Scale,
  Settings2,
  ShieldCheck,
  Trash2,
  UserRound,
  Utensils,
} from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import {
  confirmAccountDeletion,
  createReminder,
  deleteReminder,
  downloadAccountExport,
  fetchNutritionGoal,
  fetchProfile,
  fetchProfileStats,
  fetchReminders,
  requestAccountDeletion,
  updateNutritionGoal,
  updateProfileSettings,
  updateReminder,
  type AfterFoodAddAction,
  type DeletionChallenge,
  type NumberFormat,
  type NutritionGoal,
  type Profile,
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
  { value: "stay", label: "Остаться" },
] as const;
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

interface GoalDraft {
  energy_kcal: string;
  protein_g: string;
  fat_g: string;
  carbs_g: string;
}

interface ReminderEditorProps {
  type: ReminderType;
  reminder?: Reminder;
  pending: boolean;
  onSave: (type: ReminderType, time: string, weekdays: number[]) => Promise<void>;
  onToggle: (reminder: Reminder, enabled: boolean) => Promise<void>;
  onDelete: (reminder: Reminder) => Promise<void>;
}

function messageFrom(error: unknown): string {
  return error instanceof Error ? error.message : "Произошла ошибка";
}

function mutationKey(): string {
  return `${Date.now()}-${crypto.randomUUID()}`;
}

function ReminderEditor({
  type,
  reminder,
  pending,
  onSave,
  onToggle,
  onDelete,
}: ReminderEditorProps) {
  const [time, setTime] = useState(reminder?.time_local ?? (type === "weigh_in" ? "8:00" : "20:00"));
  const [weekdays, setWeekdays] = useState<number[]>(reminder?.weekdays ?? [0, 1, 2, 3, 4, 5, 6]);
  const isWeighIn = type === "weigh_in";

  const toggleWeekday = (weekday: number) => {
    setWeekdays((current) =>
      current.includes(weekday)
        ? current.filter((item) => item !== weekday)
        : [...current, weekday].sort(),
    );
  };

  return (
    <div className="reminder-editor">
      <div className="reminder-editor__heading">
        <span className="reminder-editor__icon">
          {isWeighIn ? <Scale aria-hidden="true" /> : <Salad aria-hidden="true" />}
        </span>
        <div>
          <strong>{isWeighIn ? "Взвешивание" : "Проверка рациона"}</strong>
          <small>{isWeighIn ? "Если вес еще не записан" : "Сводка по дневному рациону"}</small>
        </div>
        {reminder && (
          <label className="compact-switch" title={reminder.enabled ? "Выключить" : "Включить"}>
            <span className="sr-only">Включить напоминание</span>
            <input
              type="checkbox"
              checked={reminder.enabled}
              disabled={pending}
              onChange={(event) => void onToggle(reminder, event.target.checked)}
            />
          </label>
        )}
      </div>
      <FormField
        label="Время"
        htmlFor={`reminder-time-${type}`}
        hint="Можно вводить 8:00 или 08:00"
      >
        <input
          id={`reminder-time-${type}`}
          inputMode="numeric"
          value={time}
          placeholder="8:00"
          onChange={(event) => setTime(event.target.value)}
        />
      </FormField>
      <fieldset className="weekday-fieldset">
        <legend>Дни недели</legend>
        <div className="weekday-picker">
          {WEEKDAYS.map((label, index) => (
            <button
              key={label}
              type="button"
              className={weekdays.includes(index) ? "is-active" : ""}
              aria-pressed={weekdays.includes(index)}
              onClick={() => toggleWeekday(index)}
            >
              {label}
            </button>
          ))}
        </div>
      </fieldset>
      <div className="inline-actions">
        <button
          type="button"
          className="button-primary button-with-icon"
          disabled={pending || weekdays.length === 0 || time.trim().length < 4}
          onClick={() => void onSave(type, time, weekdays)}
        >
          <Check aria-hidden="true" size={18} />
          {reminder ? "Сохранить" : "Создать"}
        </button>
        {reminder && (
          <button
            type="button"
            className="button-text button-text--danger"
            disabled={pending}
            onClick={() => void onDelete(reminder)}
          >
            <Trash2 aria-hidden="true" size={17} />
            Удалить
          </button>
        )}
      </div>
    </div>
  );
}

export function ProfilePage() {
  const {
    user,
    initData,
    preferences,
    isDevelopmentPreview,
    preferencesPending,
    updatePreferences,
  } = useMiniAppContext();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const authorized = initData.length > 0;
  const fallbackProfile: Profile = {
    ...(user ?? {
      id: "preview",
      telegram_id: "preview",
      username: "preview",
      first_name: "Алексей",
      last_name: null,
      language_code: "ru",
      timezone: "Europe/Moscow",
      app_version: "dev",
    }),
    photo_url: null,
    number_format: "automatic",
    after_food_add_action: "open_today",
    confirm_deletions: true,
    reminders_enabled: false,
  };
  const [previewProfile, setPreviewProfile] = useState(fallbackProfile);
  const [previewGoal, setPreviewGoal] = useState<NutritionGoal | null>(null);
  const [previewReminders, setPreviewReminders] = useState<Reminder[]>([]);
  const [editedGoalDraft, setEditedGoalDraft] = useState<GoalDraft | null>(null);
  const [deleteWarningOpen, setDeleteWarningOpen] = useState(false);
  const [deletionChallenge, setDeletionChallenge] = useState<DeletionChallenge | null>(null);
  const [deletionPhrase, setDeletionPhrase] = useState("");

  const profileQuery = useQuery({
    queryKey: ["profile"],
    queryFn: () => fetchProfile(initData),
    enabled: authorized,
    retry: false,
  });
  const statsQuery = useQuery({
    queryKey: ["profile-stats"],
    queryFn: () => fetchProfileStats(initData),
    enabled: authorized,
    retry: false,
  });
  const goalQuery = useQuery({
    queryKey: ["nutrition-goal"],
    queryFn: () => fetchNutritionGoal(initData),
    enabled: authorized,
    retry: false,
  });
  const remindersQuery = useQuery({
    queryKey: ["reminders"],
    queryFn: () => fetchReminders(initData),
    enabled: authorized,
    retry: false,
  });

  const profileMutation = useMutation({
    mutationFn: (update: ProfileSettingsUpdate) => updateProfileSettings(initData, update),
    onSuccess: (profile) => queryClient.setQueryData(["profile"], profile),
  });
  const goalMutation = useMutation({
    mutationFn: (draft: GoalDraft | null) =>
      updateNutritionGoal(
        initData,
        draft
          ? {
              enabled: true,
              energy_kcal: draft.energy_kcal.trim() || null,
              protein_g: draft.protein_g.trim() || null,
              fat_g: draft.fat_g.trim() || null,
              carbs_g: draft.carbs_g.trim() || null,
            }
          : { enabled: false },
      ),
    onSuccess: (goal) => queryClient.setQueryData(["nutrition-goal"], goal),
  });
  const reminderMutation = useMutation({
    mutationFn: async ({
      type,
      time,
      weekdays,
    }: {
      type: ReminderType;
      time: string;
      weekdays: number[];
    }) => {
      const existing = (remindersQuery.data ?? []).find((item) => item.type === type);
      return existing
        ? updateReminder(initData, existing.id, { time_local: time, weekdays })
        : createReminder(initData, { type, time_local: time, weekdays }, mutationKey());
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["reminders"] });
      void queryClient.invalidateQueries({ queryKey: ["profile"] });
    },
  });
  const toggleReminderMutation = useMutation({
    mutationFn: ({ reminder, enabled }: { reminder: Reminder; enabled: boolean }) =>
      updateReminder(initData, reminder.id, { enabled }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["reminders"] });
      void queryClient.invalidateQueries({ queryKey: ["profile"] });
    },
  });
  const removeReminderMutation = useMutation({
    mutationFn: (reminder: Reminder) => deleteReminder(initData, reminder.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["reminders"] });
      void queryClient.invalidateQueries({ queryKey: ["profile"] });
    },
  });
  const deletionRequestMutation = useMutation({
    mutationFn: () => requestAccountDeletion(initData, mutationKey()),
  });
  const deletionConfirmMutation = useMutation({
    mutationFn: ({ challenge, phrase }: { challenge: DeletionChallenge; phrase: string }) =>
      confirmAccountDeletion(initData, challenge, phrase, mutationKey()),
  });

  const profile = authorized ? profileQuery.data : previewProfile;
  const stats = authorized ? (statsQuery.data ?? EMPTY_STATS) : EMPTY_STATS;
  const goal = authorized ? goalQuery.data : previewGoal;
  const reminders = authorized ? (remindersQuery.data ?? []) : previewReminders;

  const goalDraft = editedGoalDraft ?? {
    energy_kcal: goal?.energy_kcal ?? "",
    protein_g: goal?.protein_g ?? "",
    fat_g: goal?.fat_g ?? "",
    carbs_g: goal?.carbs_g ?? "",
  };

  const savePreferences = async (update: UIPreferencesUpdate) => {
    try {
      await updatePreferences(update);
      showToast("Настройки сохранены");
    } catch (error) {
      showToast(messageFrom(error), "error");
    }
  };

  const saveProfile = async (update: ProfileSettingsUpdate) => {
    try {
      if (authorized) await profileMutation.mutateAsync(update);
      else setPreviewProfile((current) => ({ ...current, ...update }));
      showToast("Настройки сохранены");
    } catch (error) {
      showToast(messageFrom(error), "error");
    }
  };

  const saveGoal = async () => {
    try {
      if (authorized) await goalMutation.mutateAsync(goalDraft);
      else {
        setPreviewGoal({ id: "preview", ...goalDraft, effective_from: new Date().toISOString().slice(0, 10), effective_to: null });
      }
      showToast("Цели питания сохранены");
    } catch (error) {
      showToast(messageFrom(error), "error");
    }
  };

  const disableGoal = async () => {
    try {
      if (authorized) await goalMutation.mutateAsync(null);
      else setPreviewGoal(null);
      setEditedGoalDraft(null);
      showToast("Цели питания отключены");
    } catch (error) {
      showToast(messageFrom(error), "error");
    }
  };

  const saveReminder = async (type: ReminderType, time: string, weekdays: number[]) => {
    try {
      if (authorized) await reminderMutation.mutateAsync({ type, time, weekdays });
      else {
        setPreviewReminders((current) => {
          const item: Reminder = {
            id: current.find((candidate) => candidate.type === type)?.id ?? type,
            type,
            enabled: true,
            time_local: time.length === 4 ? `0${time}` : time,
            weekdays,
            updated_at: new Date().toISOString(),
          };
          return [...current.filter((candidate) => candidate.type !== type), item];
        });
      }
      showToast("Напоминание сохранено");
    } catch (error) {
      showToast(messageFrom(error), "error");
    }
  };

  const toggleReminder = async (reminder: Reminder, enabled: boolean) => {
    try {
      if (authorized) await toggleReminderMutation.mutateAsync({ reminder, enabled });
      else setPreviewReminders((current) => current.map((item) => item.id === reminder.id ? { ...item, enabled } : item));
      showToast(enabled ? "Напоминание включено" : "Напоминание выключено");
    } catch (error) {
      showToast(messageFrom(error), "error");
    }
  };

  const removeReminder = async (reminder: Reminder) => {
    try {
      if (authorized) await removeReminderMutation.mutateAsync(reminder);
      else setPreviewReminders((current) => current.filter((item) => item.id !== reminder.id));
      showToast("Напоминание удалено");
    } catch (error) {
      showToast(messageFrom(error), "error");
    }
  };

  const exportData = async () => {
    if (!authorized) {
      showToast("Экспорт доступен после открытия через Telegram", "error");
      return;
    }
    try {
      const blob = await downloadAccountExport(initData);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = "wtrackerbot-data.json";
      anchor.click();
      URL.revokeObjectURL(url);
      showToast("Экспорт подготовлен");
    } catch (error) {
      showToast(messageFrom(error), "error");
    }
  };

  const beginDeletion = async () => {
    if (deletionRequestMutation.isPending) return;
    setDeleteWarningOpen(false);
    if (!authorized) {
      showToast("Удаление доступно после открытия через Telegram", "error");
      return;
    }
    try {
      const challenge = await deletionRequestMutation.mutateAsync();
      setDeletionChallenge(challenge);
      setDeletionPhrase("");
    } catch (error) {
      showToast(messageFrom(error), "error");
    }
  };

  const confirmDeletion = async () => {
    if (!deletionChallenge) return;
    try {
      await deletionConfirmMutation.mutateAsync({
        challenge: deletionChallenge,
        phrase: deletionPhrase,
      });
      setDeletionChallenge(null);
      setDeletionPhrase("");
      setEditedGoalDraft(null);
      await queryClient.invalidateQueries();
      showToast("Все данные удалены");
    } catch (error) {
      showToast(messageFrom(error), "error");
    }
  };

  const loading = authorized && [profileQuery, statsQuery, goalQuery, remindersQuery].some((query) => query.isPending);
  const failed = [profileQuery, statsQuery, goalQuery, remindersQuery].find((query) => query.error)?.error;
  if (loading) return <div className="page"><Skeleton lines={6} /></div>;
  if (authorized && failed) {
    return (
      <div className="page">
        <ErrorState
          title="Не удалось загрузить профиль"
          message={messageFrom(failed)}
          onRetry={() => {
            void profileQuery.refetch();
            void statsQuery.refetch();
            void goalQuery.refetch();
            void remindersQuery.refetch();
          }}
        />
      </div>
    );
  }
  if (!profile) return null;

  const name = [profile.first_name, profile.last_name].filter(Boolean).join(" ");
  const reminderPending = reminderMutation.isPending || toggleReminderMutation.isPending || removeReminderMutation.isPending;
  const remindersEnabled = reminders.some((item) => item.enabled);

  return (
    <div className="page page--profile">
      <section className="profile-summary" aria-labelledby="profile-name">
        <span className="profile-avatar">
          {profile.photo_url ? <img src={profile.photo_url} alt="" /> : <UserRound aria-hidden="true" />}
        </span>
        <div className="profile-identity">
          <h1 id="profile-name">{name || profile.username || "Профиль"}</h1>
          <p>{profile.username ? `@${profile.username}` : isDevelopmentPreview ? "Режим разработки" : `Telegram ID ${profile.telegram_id}`}</p>
        </div>
        <span className={`status-badge ${remindersEnabled ? "is-enabled" : ""}`}>
          {remindersEnabled ? "Напоминания вкл." : "Напоминания выкл."}
        </span>
      </section>

      <section className="profile-stats" aria-label="Статистика профиля">
        <div><CalendarDays aria-hidden="true" /><strong>{stats.diary_days}</strong><span>дней</span></div>
        <div><Salad aria-hidden="true" /><strong>{stats.ingredients}</strong><span>ингредиентов</span></div>
        <div><Utensils aria-hidden="true" /><strong>{stats.dishes}</strong><span>блюд</span></div>
        <div><Scale aria-hidden="true" /><strong>{stats.weight_entries}</strong><span>измерений</span></div>
      </section>

      <section className="settings-section" aria-labelledby="appearance-title">
        <div className="settings-title"><Moon aria-hidden="true" size={18} /><h2 id="appearance-title">Внешний вид</h2></div>
        <div className="setting-control">
          <span>Тема</span>
          <SegmentedControl label="Тема приложения" options={THEME_OPTIONS} value={preferences.theme_mode} onChange={(value: ThemeMode) => void savePreferences({ theme_mode: value })} />
        </div>
        <label className="switch-row">
          <span><strong>Компактные списки</strong><small>Больше записей помещается на экране</small></span>
          <input type="checkbox" checked={preferences.compact_lists} disabled={preferencesPending} onChange={(event) => void savePreferences({ compact_lists: event.target.checked })} />
        </label>
      </section>

      <section className="settings-section" aria-labelledby="ration-settings-title">
        <div className="settings-title"><Settings2 aria-hidden="true" size={18} /><h2 id="ration-settings-title">Рацион</h2></div>
        <div className="settings-form-grid">
          <FormField label="Часовой пояс" htmlFor="timezone" hint="Используется для дат и напоминаний">
            <select id="timezone" value={profile.timezone} disabled={profileMutation.isPending} onChange={(event) => void saveProfile({ timezone: event.target.value })}>
              {!TIMEZONES.includes(profile.timezone) && <option value={profile.timezone}>{profile.timezone}</option>}
              {TIMEZONES.map((timezone) => <option key={timezone} value={timezone}>{timezone}</option>)}
            </select>
          </FormField>
          <div className="setting-control">
            <span>Отображение чисел</span>
            <SegmentedControl label="Количество знаков после запятой" options={NUMBER_OPTIONS} value={profile.number_format} onChange={(value: NumberFormat) => void saveProfile({ number_format: value })} />
          </div>
          <div className="setting-control settings-form-grid__wide">
            <span>После добавления еды</span>
            <SegmentedControl label="Действие после добавления еды" options={AFTER_ADD_OPTIONS} value={profile.after_food_add_action} onChange={(value: AfterFoodAddAction) => void saveProfile({ after_food_add_action: value })} />
          </div>
        </div>
        <label className="switch-row">
          <span><strong>Подтверждать удаление</strong><small>Запрашивать подтверждение перед удалением записей</small></span>
          <input type="checkbox" checked={profile.confirm_deletions} disabled={profileMutation.isPending} onChange={(event) => void saveProfile({ confirm_deletions: event.target.checked })} />
        </label>
      </section>

      <section className="settings-section" aria-labelledby="goals-title">
        <div className="settings-title"><Goal aria-hidden="true" size={18} /><h2 id="goals-title">Цели питания</h2></div>
        <div className="goal-grid">
          <FormField label="Калории" htmlFor="goal-energy"><input id="goal-energy" inputMode="decimal" placeholder="2000" value={goalDraft.energy_kcal} onChange={(event) => setEditedGoalDraft({ ...goalDraft, energy_kcal: event.target.value })} /></FormField>
          <FormField label="Белки, г" htmlFor="goal-protein"><input id="goal-protein" inputMode="decimal" placeholder="120" value={goalDraft.protein_g} onChange={(event) => setEditedGoalDraft({ ...goalDraft, protein_g: event.target.value })} /></FormField>
          <FormField label="Жиры, г" htmlFor="goal-fat"><input id="goal-fat" inputMode="decimal" placeholder="70" value={goalDraft.fat_g} onChange={(event) => setEditedGoalDraft({ ...goalDraft, fat_g: event.target.value })} /></FormField>
          <FormField label="Углеводы, г" htmlFor="goal-carbs"><input id="goal-carbs" inputMode="decimal" placeholder="250" value={goalDraft.carbs_g} onChange={(event) => setEditedGoalDraft({ ...goalDraft, carbs_g: event.target.value })} /></FormField>
        </div>
        <div className="inline-actions">
          <button type="button" className="button-primary button-with-icon" disabled={goalMutation.isPending || Object.values(goalDraft).every((value) => !value.trim())} onClick={() => void saveGoal()}><Check aria-hidden="true" size={18} />Сохранить цели</button>
          {goal && <button type="button" className="button-text" disabled={goalMutation.isPending} onClick={() => void disableGoal()}>Отключить</button>}
        </div>
      </section>

      <section className="settings-section" aria-labelledby="reminders-title">
        <div className="settings-title"><Bell aria-hidden="true" size={18} /><h2 id="reminders-title">Напоминания</h2></div>
        <p className="section-description">Время применяется в часовом поясе {profile.timezone}. Изменения подхватываются планировщиком автоматически.</p>
        <div className="reminders-grid">
          {(["weigh_in", "nutrition"] as ReminderType[]).map((type) => (
            <ReminderEditor
              key={`${type}:${reminders.find((item) => item.type === type)?.updated_at ?? "new"}`}
              type={type}
              reminder={reminders.find((item) => item.type === type)}
              pending={reminderPending}
              onSave={saveReminder}
              onToggle={toggleReminder}
              onDelete={removeReminder}
            />
          ))}
        </div>
      </section>

      <section className="settings-section" aria-labelledby="privacy-title">
        <div className="settings-title"><ShieldCheck aria-hidden="true" size={18} /><h2 id="privacy-title">Данные и приватность</h2></div>
        <div className="data-summary">
          <Database aria-hidden="true" />
          <p>Храним {stats.diary_entries} записей рациона, {stats.weight_entries} измерений веса, {stats.share_packages} пакетов обмена и {stats.imported_packages} импортов.</p>
        </div>
        <div className="action-list">
          <button type="button" className="action-row" onClick={() => void exportData()}><Download aria-hidden="true" /><span><strong>Скачать мои данные</strong><small>Экспорт в формате JSON</small></span><ChevronRight aria-hidden="true" /></button>
          <Link className="action-row" to="/privacy-policy"><Info aria-hidden="true" /><span><strong>Политика конфиденциальности</strong><small>Какие данные хранит приложение</small></span><ChevronRight aria-hidden="true" /></Link>
        </div>
        <div className="danger-zone">
          <div><strong>Удалить все данные</strong><p>Рацион, продукты, вес, цели и настройки будут удалены без возможности восстановления.</p></div>
          <button type="button" className="button-danger button-with-icon" onClick={() => setDeleteWarningOpen(true)}><Trash2 aria-hidden="true" size={18} />Удалить</button>
        </div>
      </section>

      <section className="settings-section about-section" aria-labelledby="about-title">
        <div className="settings-title"><Info aria-hidden="true" size={18} /><h2 id="about-title">О приложении</h2></div>
        <div><span>WTrackerBot Mini App</span><strong>Версия {profile.app_version}</strong></div>
        <div><span>Часовой пояс</span><strong><Clock3 aria-hidden="true" size={16} />{profile.timezone}</strong></div>
      </section>

      <ConfirmDialog
        open={deleteWarningOpen}
        title="Удалить все данные?"
        description="Сначала будет создано короткоживущее подтверждение. После этого потребуется вручную ввести контрольную фразу. Это действие необратимо."
        confirmLabel={deletionRequestMutation.isPending ? "Подготовка…" : "Продолжить"}
        destructive
        onClose={() => setDeleteWarningOpen(false)}
        onConfirm={() => void beginDeletion()}
      />
      <BottomSheet open={deletionChallenge !== null} title="Подтверждение удаления" onClose={() => setDeletionChallenge(null)}>
        {deletionChallenge && (
          <div className="deletion-confirmation">
            <p>Введите фразу <strong>{deletionChallenge.confirmation_phrase}</strong>. Подтверждение действует 10 минут.</p>
            <FormField label="Контрольная фраза" htmlFor="deletion-phrase">
              <input id="deletion-phrase" autoComplete="off" value={deletionPhrase} onChange={(event) => setDeletionPhrase(event.target.value)} />
            </FormField>
            <button type="button" className="button-danger button-with-icon" disabled={deletionConfirmMutation.isPending || deletionPhrase !== deletionChallenge.confirmation_phrase} onClick={() => void confirmDeletion()}><Trash2 aria-hidden="true" size={18} />{deletionConfirmMutation.isPending ? "Удаление…" : "Удалить навсегда"}</button>
          </div>
        )}
      </BottomSheet>
    </div>
  );
}
