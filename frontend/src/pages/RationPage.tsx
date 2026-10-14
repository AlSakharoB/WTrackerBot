import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Flame,
  Goal,
  Plus,
} from "lucide-react";
import { AnimatePresence, motion, useMotionTemplate } from "motion/react";
import { useRef, useState } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";

import {
  APIError,
  deleteRationEntry,
  fetchRationDay,
  updateRationEntry,
  type MealType,
  type NumberFormat,
  type RationDay,
  type RationEntry,
  type RationNutrition,
  type RationSource,
} from "../api/client";
import { useMiniAppContext } from "../app/context";
import { RationAddSheet } from "../components/ration/RationAddSheet";
import { RationEntrySheet } from "../components/ration/RationEntrySheet";
import { RationMeals } from "../components/ration/RationMeals";
import { RationWeek } from "../components/ration/RationWeek";
import { weekDates } from "../components/ration/weekDates";
import { moveEntryInDay } from "../components/ration/move-entry";
import { AnimatedNumber } from "../components/ui/AnimatedNumber";
import { useTweenNumber } from "../components/ui/useTweenNumber";
import {
  ConfirmDialog,
  ErrorState,
  ProgressBar,
  useToast,
} from "../components/ui";

const ZERO_NUTRITION: RationNutrition = {
  energy_kcal: "0",
  protein_g: "0",
  fat_g: "0",
  carbs_g: "0",
};
const MEALS: Array<{ type: MealType; label: string }> = [
  { type: "breakfast", label: "Завтрак" },
  { type: "lunch", label: "Обед" },
  { type: "dinner", label: "Ужин" },
  { type: "snack", label: "Перекус" },
];

function todayInTimezone(timezone: string): string {
  try {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone: timezone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).formatToParts(new Date());
    const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
    return `${values.year}-${values.month}-${values.day}`;
  } catch {
    return new Date().toISOString().slice(0, 10);
  }
}

function emptyDay(date: string, today: string, timezone: string): RationDay {
  return {
    date,
    timezone,
    number_format: "automatic",
    is_today: date === today,
    is_future: date > today,
    entry_count: 0,
    totals: ZERO_NUTRITION,
    macro_percentages: { protein: 0, fat: 0, carbs: 0 },
    goal: null,
    meals: MEALS.map((meal) => ({
      ...meal,
      totals: ZERO_NUTRITION,
      entries: [],
    })),
  };
}

function numeric(value: string | null): number {
  const parsed = Number(value ?? 0);
  return Number.isFinite(parsed) ? parsed : 0;
}

function formatValue(value: string | number, format: NumberFormat): string {
  const digits = format === "one_decimal" ? 1 : 2;
  return new Intl.NumberFormat("ru-RU", {
    minimumFractionDigits: format === "automatic" ? 0 : digits,
    maximumFractionDigits: digits,
  }).format(typeof value === "number" ? value : numeric(value));
}

function percentage(current: string, target: string | null): number {
  const targetValue = numeric(target);
  return targetValue > 0 ? numeric(current) / targetValue * 100 : 0;
}

function MacroOverview({ day }: { day: RationDay }) {
  const { totals, macro_percentages: macros, number_format: format } = day;
  const energyText = formatValue(totals.energy_kcal, format);
  const energyDigits = energyText.replace(/\s/g, "").length;
  const energySize = energyDigits >= 9
    ? "is-extra-compact"
    : energyDigits >= 7
      ? "is-compact"
      : "";
  const hasMacros = macros.protein + macros.fat + macros.carbs > 0;
  const proteinEnd = Math.min(100, Math.max(0, macros.protein));
  const fatEnd = Math.min(100, Math.max(proteinEnd, proteinEnd + macros.fat));
  const animatedProtein = useTweenNumber(proteinEnd);
  const animatedFat = useTweenNumber(fatEnd);
  const background = useMotionTemplate`conic-gradient(var(--color-macro-protein) 0 ${animatedProtein}%, var(--color-macro-fat) ${animatedProtein}% ${animatedFat}%, var(--color-macro-carbs) ${animatedFat}% 100%)`;
  return (
    <div className="macro-overview">
      <motion.div
        className={`macro-ring ${hasMacros ? "" : "is-empty"} ${energySize}`}
        style={{ background: hasMacros ? background : undefined }}
        role="img"
        aria-label={`${energyText} ккал. ${hasMacros ? `Белки ${macros.protein}%, жиры ${macros.fat}%, углеводы ${macros.carbs}%` : "Данные о БЖУ отсутствуют"}`}
      >
        <div>
          <AnimatedNumber value={numeric(totals.energy_kcal)} format={format} energy />
          <span>{day.goal?.energy_kcal ? `из ${formatValue(day.goal.energy_kcal, format)} ккал` : "ккал"}</span>
          {!hasMacros && <small>Нет данных БЖУ</small>}
        </div>
      </motion.div>
      <div className="macro-legend">
        <div className="macro-legend__protein"><i aria-hidden="true" /><span>Белки <small>{macros.protein}%</small></span><strong><AnimatedNumber value={numeric(totals.protein_g)} format={format} suffix=" г" /><small>{day.goal?.protein_g ? `/ ${formatValue(day.goal.protein_g, format)} г` : "· цель не задана"}</small></strong></div>
        <div className="macro-legend__fat"><i aria-hidden="true" /><span>Жиры <small>{macros.fat}%</small></span><strong><AnimatedNumber value={numeric(totals.fat_g)} format={format} suffix=" г" /><small>{day.goal?.fat_g ? `/ ${formatValue(day.goal.fat_g, format)} г` : "· цель не задана"}</small></strong></div>
        <div className="macro-legend__carbs"><i aria-hidden="true" /><span>Углеводы <small>{macros.carbs}%</small></span><strong><AnimatedNumber value={numeric(totals.carbs_g)} format={format} suffix=" г" /><small>{day.goal?.carbs_g ? `/ ${formatValue(day.goal.carbs_g, format)} г` : "· цель не задана"}</small></strong></div>
      </div>
    </div>
  );
}

function DayBalance({ day }: { day: RationDay }) {
  const energyGoal = day.goal?.energy_kcal ?? null;
  const hasEnergyGoal = energyGoal !== null && numeric(energyGoal) > 0;
  const difference = hasEnergyGoal
    ? numeric(energyGoal) - numeric(day.totals.energy_kcal)
    : null;
  const progress = hasEnergyGoal
    ? percentage(day.totals.energy_kcal, energyGoal)
    : 0;
  const isExcess = difference !== null && difference < 0;
  const statusLabel = difference === null
    ? "Цели не заданы"
    : isExcess
      ? "Цель превышена на"
      : difference === 0
        ? "Цель выполнена"
        : "Осталось";

  return (
    <section className="ration-balance" aria-labelledby="daily-summary-title">
      <div className="ration-balance__heading">
        <div>
          <span>Итог дня</span>
          <h1 id="daily-summary-title">Баланс КБЖУ</h1>
          <small>{day.entry_count} записей · {day.timezone}</small>
        </div>
        <div className="ration-balance__status-group">
          {day.is_future && <span className="future-badge">Будущий день</span>}
          <div className={`ration-balance__status ${isExcess ? "is-excess" : ""}`}>
            {isExcess ? <Flame aria-hidden="true" /> : <Goal aria-hidden="true" />}
            <span>
              {statusLabel}
              {difference !== null && (
                <strong>{isExcess ? "+" : ""}{formatValue(Math.abs(difference), day.number_format)} ккал</strong>
              )}
            </span>
          </div>
        </div>
      </div>
      <MacroOverview key={day.date} day={day} />
      {hasEnergyGoal ? (
        <div className="ration-energy-progress">
          <span>Калории</span>
          <ProgressBar label="Выполнение цели по калориям" value={progress} />
          <strong>{formatValue(day.totals.energy_kcal, day.number_format)} / {formatValue(energyGoal, day.number_format)} <small>ккал</small></strong>
          <b className={isExcess ? "is-excess" : ""}>{Math.round(progress)}%</b>
        </div>
      ) : (
        <div className="ration-goal-missing">
          <span>Добавьте цели, чтобы сравнивать дневной рацион.</span>
          <Link to="/profile">Настроить</Link>
        </div>
      )}
    </section>
  );
}

function RationPageSkeleton() {
  return (
    <>
      <section className="ration-balance ration-page-skeleton" aria-busy="true" aria-label="Загрузка рациона">
        <span className="sr-only">Загрузка рациона</span>
        <i /><i /><i /><i />
      </section>
      <section className="ration-meals ration-meals-skeleton" aria-hidden="true">
        <i /><i /><i />
      </section>
    </>
  );
}

export function RationPage() {
  const { user, profile, initData, hapticFeedback } = useMiniAppContext();
  const { showToast } = useToast();
  const queryClient = useQueryClient();
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const timezone = user?.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone ?? "UTC";
  const today = todayInTimezone(timezone);
  const requestedDate = searchParams.get("date");
  const initialDate = requestedDate && /^\d{4}-\d{2}-\d{2}$/.test(requestedDate) ? requestedDate : today;
  const [date, setDate] = useState(initialDate);
  const [selectedEntry, setSelectedEntry] = useState<RationEntry | null>(null);
  const [deletingEntry, setDeletingEntry] = useState<{ entry: RationEntry; date: string } | null>(null);
  const saving = useRef(false);
  const authorized = initData.length > 0;
  const addOpen = location.pathname === "/ration/add";
  const requestedMeal = searchParams.get("meal") as MealType | null;
  const initialMeal = MEALS.some((item) => item.type === requestedMeal) ? requestedMeal! : "other";
  const locationState = location.state as { createdRationSource?: RationSource } | null;
  const initialSource = locationState?.createdRationSource ?? null;
  const rationQuery = useQuery({
    queryKey: ["ration", date],
    queryFn: () => fetchRationDay(initData, date),
    enabled: authorized,
    retry: false,
  });
  const day = authorized ? rationQuery.data : emptyDay(date, today, timezone);
  const moveMutation = useMutation({
    mutationFn: ({ entry, meal }: { entry: RationEntry; meal: MealType; date: string }) => updateRationEntry(initData, entry.id, { expected_updated_at: entry.updated_at, meal_type: meal }),
    onMutate: async ({ entry, meal, date: affectedDate }) => {
      const queryKey = ["ration", affectedDate];
      await queryClient.cancelQueries({ queryKey });
      const previous = queryClient.getQueryData<RationDay>(queryKey);
      queryClient.setQueryData<RationDay>(queryKey, (current) => current ? moveEntryInDay(current, entry.id, meal) : current);
      return { previous };
    },
    onSuccess: () => { hapticFeedback?.("success"); showToast("Запись перенесена"); },
    onError: (error, variables, context) => {
      if (context?.previous) queryClient.setQueryData(["ration", variables.date], context.previous);
      showToast(error instanceof APIError && error.status === 409 ? "Запись уже изменилась. Рацион обновлён, повторите перенос." : error.message, "error");
    },
    onSettled: async (_data, _error, variables) => {
      await queryClient.invalidateQueries({ queryKey: ["ration", variables.date] });
      saving.current = false;
    },
  });
  const deleteMutation = useMutation({
    mutationFn: ({ entry }: { entry: RationEntry; date: string }) => deleteRationEntry(initData, entry.id),
    onSuccess: () => { setDeletingEntry(null); showToast("Запись удалена"); },
    onError: (error) => showToast(error.message, "error"),
    onSettled: async (_data, _error, variables) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["ration", variables.date] }),
        queryClient.invalidateQueries({ queryKey: ["ration-week", weekDates(variables.date)[0]] }),
      ]);
      saving.current = false;
    },
  });
  const removeEntry = (selection: { entry: RationEntry; date: string }) => {
    if (saving.current || !authorized) return;
    saving.current = true;
    deleteMutation.mutate(selection);
  };

  if (authorized && rationQuery.isPending) {
    return <div className="page page--ration"><RationWeek value={date} today={today} initData={initData} onChange={setDate} /><RationPageSkeleton /></div>;
  }
  if (authorized && rationQuery.error && !rationQuery.data) {
    return (
      <div className="page page--ration">
        <RationWeek value={date} today={today} initData={initData} onChange={setDate} />
        <ErrorState title="Не удалось загрузить рацион" message={rationQuery.error.message} onRetry={() => void rationQuery.refetch()} />
      </div>
    );
  }
  if (!day) return null;

  const addTarget = `/ration/add?date=${date}`;
  const closeAdd = () => navigate(`/ration?date=${date}`, { replace: true });
  const refreshRation = (affectedDate?: string) => {
    setSelectedEntry(null);
    void queryClient.invalidateQueries({ queryKey: ["ration", date] });
    void queryClient.invalidateQueries({ queryKey: ["ration-week"] });
    if (affectedDate && affectedDate !== date) {
      void queryClient.invalidateQueries({ queryKey: ["ration", affectedDate] });
    }
  };
  const refreshSelectedEntry = async (entryId: string) => {
    const refreshed = await rationQuery.refetch();
    const freshEntry = refreshed.data?.meals
      .flatMap((meal) => meal.entries)
      .find((entry) => entry.id === entryId) ?? null;
    setSelectedEntry(freshEntry);
  };

  return (
    <div className="page page--ration">
      <RationWeek value={date} today={today} initData={initData} day={day} onChange={setDate} />

      <DayBalance day={day} />

      <section className="ration-meals" aria-labelledby="meals-title">
        <div className="section-heading"><div><h2 id="meals-title">Приёмы пищи</h2><p>{day.entry_count === 0 ? "Рацион пока пуст" : `Всего записей: ${day.entry_count}`}</p></div><Link className="button-primary button-with-icon" to={addTarget}><Plus aria-hidden="true" size={18} />Добавить</Link></div>
        <RationMeals key={date} meals={day.meals} date={date} format={day.number_format} formatValue={formatValue} disabled={!authorized || moveMutation.isPending || deleteMutation.isPending} onPickUp={() => hapticFeedback?.("selection")} onSelectEntry={setSelectedEntry} onMoveEntry={(entry, meal) => {
          if (saving.current || !authorized) return;
          saving.current = true;
          moveMutation.mutate({ entry, meal, date });
        }} onDeleteEntry={(entry) => {
          if (profile.confirm_deletions) setDeletingEntry({ entry, date });
          else removeEntry({ entry, date });
        }} />
      </section>

      <AnimatePresence mode="wait" propagate={addOpen}>
      {addOpen && <RationAddSheet
        key={`${date}-${initialMeal}-${initialSource?.type ?? "none"}-${initialSource?.id ?? "none"}`}
        open={addOpen}
        date={date}
        initialMeal={initialMeal}
        initialSource={initialSource}
        format={day.number_format}
        initData={initData}
        authorized={authorized}
        stayOpenAfterSave={profile.after_food_add_action === "stay"}
        formatValue={formatValue}
        onClose={closeAdd}
        onSaved={() => {
          refreshRation();
          if (profile.after_food_add_action === "open_today") {
            setDate(today);
            navigate(`/ration?date=${today}`, { replace: true });
          }
        }}
      />}
      </AnimatePresence>
      <AnimatePresence mode="wait" propagate={selectedEntry !== null}>
      {selectedEntry && <RationEntrySheet
        key={`${selectedEntry?.id ?? "none"}-${selectedEntry?.updated_at ?? "none"}-${date}`}
        entry={selectedEntry}
        currentDate={date}
        format={day.number_format}
        initData={initData}
        authorized={authorized}
        confirmDeletions={profile.confirm_deletions}
        formatValue={formatValue}
        onClose={() => setSelectedEntry(null)}
        onChanged={refreshRation}
        onConflictRefresh={refreshSelectedEntry}
      />}
      </AnimatePresence>
      <ConfirmDialog open={deletingEntry !== null} title="Удалить запись?" description={`${deletingEntry?.entry.source_name ?? "Запись"} будет удалён из рациона за этот день.`} confirmLabel={deleteMutation.isPending ? "Удаляем..." : "Удалить"} confirmDisabled={deleteMutation.isPending} destructive onClose={() => { if (!deleteMutation.isPending) setDeletingEntry(null); }} onConfirm={() => { if (deletingEntry) removeEntry(deletingEntry); }} />
    </div>
  );
}
