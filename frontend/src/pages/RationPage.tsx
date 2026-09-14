import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Apple,
  CookingPot,
  EllipsisVertical,
  Flame,
  Goal,
  MoonStar,
  Plus,
  Salad,
  Sun,
  Sunrise,
  Utensils,
} from "lucide-react";
import { useState, type CSSProperties, type ElementType } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";

import {
  fetchRationDay,
  type MealType,
  type NumberFormat,
  type RationDay,
  type RationEntry,
  type RationMeal,
  type RationNutrition,
  type RationSource,
} from "../api/client";
import { useMiniAppContext } from "../app/context";
import { RationAddSheet } from "../components/ration/RationAddSheet";
import { RationEntrySheet } from "../components/ration/RationEntrySheet";
import {
  DateSwitcher,
  ErrorState,
  ProgressBar,
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
const MEAL_ICONS: Record<MealType, ElementType> = {
  breakfast: Sunrise,
  lunch: Sun,
  dinner: MoonStar,
  snack: Apple,
  other: Utensils,
};

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
  const hasMacros = macros.protein + macros.fat + macros.carbs > 0;
  const proteinEnd = Math.min(100, Math.max(0, macros.protein));
  const fatEnd = Math.min(100, Math.max(proteinEnd, proteinEnd + macros.fat));
  const chartStyle: CSSProperties = hasMacros
    ? {
        background: `conic-gradient(var(--color-macro-protein) 0 ${proteinEnd}%, var(--color-macro-fat) ${proteinEnd}% ${fatEnd}%, var(--color-macro-carbs) ${fatEnd}% 100%)`,
      }
    : {};
  return (
    <div className="macro-overview">
      <div
        className={`macro-ring ${hasMacros ? "" : "is-empty"}`}
        style={chartStyle}
        role="img"
        aria-label={hasMacros ? `Белки ${macros.protein}%, жиры ${macros.fat}%, углеводы ${macros.carbs}%` : "Данные о БЖУ отсутствуют"}
      >
        <div>
          <strong>{formatValue(totals.energy_kcal, format)}</strong>
          <span>{day.goal?.energy_kcal ? `из ${formatValue(day.goal.energy_kcal, format)} ккал` : "ккал"}</span>
          {!hasMacros && <small>Нет данных БЖУ</small>}
        </div>
      </div>
      <div className="macro-legend">
        <div className="macro-legend__protein"><i aria-hidden="true" /><span>Белки <small>{macros.protein}%</small></span><strong>{formatValue(totals.protein_g, format)} г <small>{day.goal?.protein_g ? `/ ${formatValue(day.goal.protein_g, format)} г` : "· цель не задана"}</small></strong></div>
        <div className="macro-legend__fat"><i aria-hidden="true" /><span>Жиры <small>{macros.fat}%</small></span><strong>{formatValue(totals.fat_g, format)} г <small>{day.goal?.fat_g ? `/ ${formatValue(day.goal.fat_g, format)} г` : "· цель не задана"}</small></strong></div>
        <div className="macro-legend__carbs"><i aria-hidden="true" /><span>Углеводы <small>{macros.carbs}%</small></span><strong>{formatValue(totals.carbs_g, format)} г <small>{day.goal?.carbs_g ? `/ ${formatValue(day.goal.carbs_g, format)} г` : "· цель не задана"}</small></strong></div>
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
      <MacroOverview day={day} />
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

function MealSection({
  meal,
  date,
  format,
  onSelectEntry,
}: {
  meal: RationMeal;
  date: string;
  format: NumberFormat;
  onSelectEntry: (entry: RationEntry) => void;
}) {
  const Icon = MEAL_ICONS[meal.type];
  const addTarget = `/ration/add?date=${date}&meal=${meal.type}`;
  return (
    <article className="meal-section">
      <header>
        <span className={`meal-icon meal-icon--${meal.type}`}><Icon aria-hidden="true" /></span>
        <div>
          <h3>{meal.label}</h3>
          <p>{formatValue(meal.totals.energy_kcal, format)} ккал · Б {formatValue(meal.totals.protein_g, format)} · Ж {formatValue(meal.totals.fat_g, format)} · У {formatValue(meal.totals.carbs_g, format)}</p>
        </div>
        <Link className="icon-link" to={addTarget} aria-label={`Добавить в ${meal.label.toLowerCase()}`} title="Добавить запись"><Plus aria-hidden="true" /></Link>
      </header>
      {meal.entries.length === 0 ? (
        <Link className="meal-empty" to={addTarget}>
          <span>Пока ничего не добавлено</span>
          <strong>Добавить еду</strong>
        </Link>
      ) : (
        <div className="meal-entries">
          {meal.entries.map((entry) => (
            <div className="meal-entry" key={entry.id}>
              <button type="button" className="meal-entry__main" aria-label={`Открыть запись ${entry.source_name}`} onClick={() => onSelectEntry(entry)}>
                <span className="meal-entry__type">{entry.type === "dish" ? <CookingPot aria-hidden="true" /> : <Salad aria-hidden="true" />}</span>
                <span className="meal-entry__copy">
                  <strong>{entry.source_name}</strong>
                  <small>{formatValue(entry.grams, format)} г{!entry.source_available && " · Источник удалён"}</small>
                </span>
                <span className="meal-entry__energy">{formatValue(entry.nutrition.energy_kcal, format)} <small>ккал</small></span>
              </button>
              <button type="button" className="icon-button icon-button--small" aria-label={`Действия с записью ${entry.source_name}`} onClick={() => onSelectEntry(entry)}><EllipsisVertical aria-hidden="true" /></button>
            </div>
          ))}
        </div>
      )}
    </article>
  );
}

function RationPageSkeleton({ date, today, onChange }: { date: string; today: string; onChange: (value: string) => void }) {
  return (
    <div className="page page--ration">
      <DateSwitcher value={date} today={today} isFuture={date > today} onChange={onChange} />
      <section className="ration-balance ration-page-skeleton" aria-busy="true" aria-label="Загрузка рациона">
        <span className="sr-only">Загрузка рациона</span>
        <i /><i /><i /><i />
      </section>
      <section className="ration-meals ration-meals-skeleton" aria-hidden="true">
        <i /><i /><i />
      </section>
    </div>
  );
}

export function RationPage() {
  const { user, profile, initData } = useMiniAppContext();
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

  if (authorized && rationQuery.isPending) {
    return <RationPageSkeleton date={date} today={today} onChange={setDate} />;
  }
  if (authorized && rationQuery.error) {
    return (
      <div className="page">
        <DateSwitcher value={date} today={today} isFuture={date > today} onChange={setDate} />
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
  const visibleMeals = day.meals.filter((meal) => meal.type !== "other" || meal.entries.length > 0);

  return (
    <div className="page page--ration">
      <DateSwitcher value={date} today={today} isFuture={day.is_future} onChange={setDate} />

      <DayBalance day={day} />

      <section className="ration-meals" aria-labelledby="meals-title">
        <div className="section-heading"><div><h2 id="meals-title">Приёмы пищи</h2><p>{day.entry_count === 0 ? "Рацион пока пуст" : `Всего записей: ${day.entry_count}`}</p></div><Link className="button-primary button-with-icon" to={addTarget}><Plus aria-hidden="true" size={18} />Добавить</Link></div>
        <div className="meals-list">
          {visibleMeals.map((meal) => <MealSection key={meal.type} meal={meal} date={date} format={day.number_format} onSelectEntry={setSelectedEntry} />)}
        </div>
      </section>

      <RationAddSheet
        key={`${addOpen}-${date}-${initialMeal}-${initialSource?.type ?? "none"}-${initialSource?.id ?? "none"}`}
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
      />
      <RationEntrySheet
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
      />
    </div>
  );
}
