import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Apple,
  CalendarPlus,
  CookingPot,
  EllipsisVertical,
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
  type RationGoal,
  type RationMeal,
  type RationNutrition,
} from "../api/client";
import { useMiniAppContext } from "../app/context";
import { RationAddSheet } from "../components/ration/RationAddSheet";
import { RationEntrySheet } from "../components/ration/RationEntrySheet";
import {
  DateSwitcher,
  ErrorState,
  ProgressBar,
  Skeleton,
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

interface GoalRowProps {
  label: string;
  current: string;
  target: string | null;
  unit: string;
  tone: "energy" | "protein" | "fat" | "carbs";
  format: NumberFormat;
}

function GoalRow({ label, current, target, unit, tone, format }: GoalRowProps) {
  if (target === null) return null;
  const progress = percentage(current, target);
  const excess = numeric(current) - numeric(target);
  return (
    <div className="goal-progress-row">
      <div>
        <strong>{label}</strong>
        <span>{formatValue(current, format)} / {formatValue(target, format)} {unit}</span>
        <b className={excess > 0 ? "is-excess" : ""}>
          {Math.round(progress)}%
          {excess > 0 && ` · +${formatValue(excess, format)} ${unit}`}
        </b>
      </div>
      <ProgressBar label={`Выполнение цели: ${label}`} value={progress} tone={tone} />
    </div>
  );
}

function MacroOverview({ day }: { day: RationDay }) {
  const { totals, macro_percentages: macros, number_format: format } = day;
  const hasMacros = macros.protein + macros.fat + macros.carbs > 0;
  const proteinEnd = macros.protein;
  const fatEnd = proteinEnd + macros.fat;
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
          <span>ккал</span>
        </div>
      </div>
      <div className="macro-legend">
        <div className="macro-legend__protein"><span>Белки</span><strong>{formatValue(totals.protein_g, format)} г</strong><b>{macros.protein}%</b></div>
        <div className="macro-legend__fat"><span>Жиры</span><strong>{formatValue(totals.fat_g, format)} г</strong><b>{macros.fat}%</b></div>
        <div className="macro-legend__carbs"><span>Углеводы</span><strong>{formatValue(totals.carbs_g, format)} г</strong><b>{macros.carbs}%</b></div>
      </div>
    </div>
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
        <div className="meal-empty">
          <span>Нет записей</span>
          <Link to={addTarget}>Добавить</Link>
        </div>
      ) : (
        <div className="meal-entries">
          {meal.entries.map((entry) => (
            <div className="meal-entry" key={entry.id}>
              <span className="meal-entry__type">{entry.type === "dish" ? <CookingPot aria-hidden="true" /> : <Salad aria-hidden="true" />}</span>
              <div>
                <strong>{entry.source_name}</strong>
                <span>{formatValue(entry.grams, format)} г{!entry.source_available && " · источник удалён"}</span>
              </div>
              <span className="meal-entry__energy">{formatValue(entry.nutrition.energy_kcal, format)} ккал</span>
              <button type="button" className="icon-button icon-button--small" aria-label={`Открыть запись ${entry.source_name}`} onClick={() => onSelectEntry(entry)}><EllipsisVertical aria-hidden="true" /></button>
            </div>
          ))}
        </div>
      )}
    </article>
  );
}

function GoalOverview({ goal, day }: { goal: RationGoal; day: RationDay }) {
  return (
    <div className="goals-progress">
      <GoalRow label="Калории" current={day.totals.energy_kcal} target={goal.energy_kcal} unit="ккал" tone="energy" format={day.number_format} />
      <GoalRow label="Белки" current={day.totals.protein_g} target={goal.protein_g} unit="г" tone="protein" format={day.number_format} />
      <GoalRow label="Жиры" current={day.totals.fat_g} target={goal.fat_g} unit="г" tone="fat" format={day.number_format} />
      <GoalRow label="Углеводы" current={day.totals.carbs_g} target={goal.carbs_g} unit="г" tone="carbs" format={day.number_format} />
    </div>
  );
}

export function RationPage() {
  const { user, initData } = useMiniAppContext();
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
  const rationQuery = useQuery({
    queryKey: ["ration", date],
    queryFn: () => fetchRationDay(initData, date),
    enabled: authorized,
    retry: false,
  });
  const day = authorized ? rationQuery.data : emptyDay(date, today, timezone);

  if (authorized && rationQuery.isPending) {
    return <div className="page"><Skeleton lines={7} /></div>;
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

  const energyGoal = numeric(day.goal?.energy_kcal ?? null);
  const energyCurrent = numeric(day.totals.energy_kcal);
  const energyDifference = energyGoal - energyCurrent;
  const addTarget = `/ration/add?date=${date}`;
  const closeAdd = () => navigate(`/ration?date=${date}`, { replace: true });
  const refreshRation = (affectedDate?: string) => {
    setSelectedEntry(null);
    void queryClient.invalidateQueries({ queryKey: ["ration", date] });
    if (affectedDate && affectedDate !== date) {
      void queryClient.invalidateQueries({ queryKey: ["ration", affectedDate] });
    }
  };

  return (
    <div className="page page--ration">
      <DateSwitcher value={date} today={today} isFuture={day.is_future} onChange={setDate} />

      <section className="section-block ration-summary" aria-labelledby="daily-summary-title">
        <div className="section-heading">
          <div><h1 id="daily-summary-title">Итоги дня</h1><p>{day.entry_count} записей · {day.timezone}</p></div>
          {day.is_future && <span className="future-badge">Будущий день</span>}
        </div>
        <div className="energy-summary">
          <div><span>Съедено</span><strong>{formatValue(day.totals.energy_kcal, day.number_format)}</strong><small>ккал</small></div>
          <div className="energy-summary__detail">
            {energyGoal > 0 ? (
              <><span>Цель {formatValue(energyGoal, day.number_format)} ккал</span><strong className={energyDifference < 0 ? "is-excess" : ""}>{energyDifference >= 0 ? "Осталось" : "Превышение"} {formatValue(Math.abs(energyDifference), day.number_format)} ккал</strong><ProgressBar label="Выполнение цели по калориям" value={percentage(day.totals.energy_kcal, day.goal?.energy_kcal ?? null)} /></>
            ) : (
              <><span>Дневная цель не задана</span><Link to="/profile">Настроить цели</Link></>
            )}
          </div>
        </div>
        <MacroOverview day={day} />
      </section>

      <section className="section-block ration-goals" aria-labelledby="ration-goals-title">
        <div className="section-heading"><div><h2 id="ration-goals-title">Дневные цели</h2><p>Выполнение калорий и БЖУ</p></div><Goal aria-hidden="true" /></div>
        {day.goal ? <GoalOverview goal={day.goal} day={day} /> : <div className="inline-empty"><span>Цели на этот день не заданы</span><Link to="/profile">Настроить</Link></div>}
      </section>

      <section className="section-block ration-meals" aria-labelledby="meals-title">
        <div className="section-heading"><div><h2 id="meals-title">Приёмы пищи</h2><p>{day.entry_count === 0 ? "Рацион пока пуст" : `Всего записей: ${day.entry_count}`}</p></div><Link className="button-primary button-with-icon" to={addTarget}><Plus aria-hidden="true" size={18} />Добавить</Link></div>
        <div className="meals-list">
          {day.meals.map((meal) => <MealSection key={meal.type} meal={meal} date={date} format={day.number_format} onSelectEntry={setSelectedEntry} />)}
        </div>
        <Link className="button-primary button-with-icon ration-add-button" to={addTarget}><CalendarPlus aria-hidden="true" size={18} />Добавить еду</Link>
      </section>

      <RationAddSheet
        key={`${addOpen}-${date}-${initialMeal}`}
        open={addOpen}
        date={date}
        initialMeal={initialMeal}
        format={day.number_format}
        initData={initData}
        authorized={authorized}
        formatValue={formatValue}
        onClose={closeAdd}
        onSaved={() => { refreshRation(); closeAdd(); }}
      />
      <RationEntrySheet
        key={`${selectedEntry?.id ?? "none"}-${date}`}
        entry={selectedEntry}
        currentDate={date}
        format={day.number_format}
        initData={initData}
        authorized={authorized}
        formatValue={formatValue}
        onClose={() => setSelectedEntry(null)}
        onChanged={refreshRation}
      />
    </div>
  );
}
