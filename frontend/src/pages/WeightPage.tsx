import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarRange, ChevronRight, Goal, Pencil, Plus, Scale } from "lucide-react";
import { useMemo, useState } from "react";

import { fetchWeightRange, type WeightEntry, type WeightRange } from "../api/client";
import { useMiniAppContext } from "../app/context";
import { EmptyState, ErrorState, MetricTile, ProgressBar, Skeleton } from "../components/ui";
import { WeightChart } from "../components/weight/WeightChart";
import { WeightEntrySheet } from "../components/weight/WeightEntrySheet";
import { WeightGoalSheet } from "../components/weight/WeightGoalSheet";

type PresetRange = 7 | 30 | 90 | 180 | 365;
type RangeChoice = PresetRange | "custom";

const RANGE_OPTIONS: Array<{ value: RangeChoice; label: string }> = [
  { value: 7, label: "7 дней" },
  { value: 30, label: "30 дней" },
  { value: 90, label: "90 дней" },
  { value: 180, label: "180 дней" },
  { value: 365, label: "365 дней" },
  { value: "custom", label: "Свой период" },
];

function dateInTimezone(value: Date, timezone: string): string {
  try {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone: timezone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).formatToParts(value);
    const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
    return `${values.year}-${values.month}-${values.day}`;
  } catch {
    return value.toISOString().slice(0, 10);
  }
}

function shiftDate(value: string, days: number): string {
  const date = new Date(`${value}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function inclusiveDays(from: string, to: string): number {
  const start = new Date(`${from}T00:00:00Z`).getTime();
  const end = new Date(`${to}T00:00:00Z`).getTime();
  return Math.floor((end - start) / 86_400_000) + 1;
}

function formatWeight(value: string | null): string {
  if (value === null) return "—";
  return Number(value).toLocaleString("ru-RU", { maximumFractionDigits: 2 });
}

function signedWeight(value: string | null): string {
  if (value === null) return "—";
  const number = Number(value);
  return `${number > 0 ? "+" : ""}${number.toLocaleString("ru-RU", { maximumFractionDigits: 2 })}`;
}

function formatMoment(value: string, timezone: string, withTime = false): string {
  return new Intl.DateTimeFormat("ru-RU", {
    timeZone: timezone,
    day: "numeric",
    month: "long",
    year: "numeric",
    ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}),
  }).format(new Date(value));
}

function formatTime(value: string, timezone: string): string {
  return new Intl.DateTimeFormat("ru-RU", {
    timeZone: timezone,
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function emptyRange(from: string, to: string, timezone: string): WeightRange {
  return {
    timezone,
    date_from: from,
    date_to: to,
    current: null,
    previous: null,
    change_from_previous_kg: null,
    period_change_kg: null,
    minimum_kg: null,
    maximum_kg: null,
    goal: null,
    points: [],
    history: [],
  };
}

function goalDetail(data: WeightRange): string {
  if (!data.goal) return "Не задана";
  if (!data.current) return "Запишите текущий вес";
  if (data.goal.progress?.achieved) return "Цель достигнута";
  const distance = Math.abs(Number(data.goal.target_weight_kg) - Number(data.current.weight_kg));
  return `Осталось ${formatWeight(String(distance))} кг`;
}

export function WeightPage() {
  const { user, initData } = useMiniAppContext();
  const queryClient = useQueryClient();
  const timezone = user?.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone ?? "UTC";
  const today = dateInTimezone(new Date(), timezone);
  const [rangeChoice, setRangeChoice] = useState<RangeChoice>(30);
  const [customFrom, setCustomFrom] = useState(shiftDate(today, -29));
  const [customTo, setCustomTo] = useState(today);
  const [appliedCustom, setAppliedCustom] = useState({ from: customFrom, to: customTo });
  const [addOpen, setAddOpen] = useState(false);
  const [goalOpen, setGoalOpen] = useState(false);
  const [selectedEntry, setSelectedEntry] = useState<WeightEntry | null>(null);
  const authorized = initData.length > 0;

  const range = useMemo(() => {
    if (rangeChoice === "custom") return appliedCustom;
    return { from: shiftDate(today, -(rangeChoice - 1)), to: today };
  }, [appliedCustom, rangeChoice, today]);
  const validCustomDates = /^\d{4}-\d{2}-\d{2}$/.test(customFrom) && /^\d{4}-\d{2}-\d{2}$/.test(customTo);
  const customDays = validCustomDates ? inclusiveDays(customFrom, customTo) : 0;
  const customError = !validCustomDates
    ? "Укажите обе даты"
    : customFrom > customTo
    ? "Начальная дата должна быть раньше конечной"
    : customDays > 365
      ? "Период не может быть больше 365 дней"
      : undefined;
  const weightQuery = useQuery({
    queryKey: ["weight", range.from, range.to],
    queryFn: () => fetchWeightRange(initData, range.from, range.to),
    enabled: authorized,
    retry: false,
  });
  const data = authorized ? weightQuery.data : emptyRange(range.from, range.to, timezone);

  if (authorized && weightQuery.isPending) return <div className="page"><Skeleton lines={7} /></div>;
  if (authorized && weightQuery.error) {
    return (
      <div className="page">
        <ErrorState title="Не удалось загрузить вес" message={weightQuery.error.message} onRetry={() => void weightQuery.refetch()} />
      </div>
    );
  }
  if (!data) return null;

  const refresh = () => {
    setAddOpen(false);
    setGoalOpen(false);
    setSelectedEntry(null);
    void queryClient.invalidateQueries({ queryKey: ["weight"] });
    void queryClient.invalidateQueries({ queryKey: ["weight-goal"] });
  };
  const change = Number(data.change_from_previous_kg ?? 0);
  const periodChange = Number(data.period_change_kg ?? 0);
  const progress = data.goal?.progress ? Number(data.goal.progress.percentage) : null;

  return (
    <div className="page page--weight">
      <section className="weight-overview" aria-labelledby="weight-summary-title">
        <div className="section-heading">
          <div>
            <h1 id="weight-summary-title">Текущий вес</h1>
            <p>{data.current ? formatMoment(data.current.measured_at, data.timezone, true) : "Нет измерений"}</p>
          </div>
          <button className="button-primary button-with-icon" type="button" onClick={() => setAddOpen(true)}>
            <Plus aria-hidden="true" size={18} /> Записать
          </button>
        </div>
        <div className="metric-grid metric-grid--weight">
          <MetricTile label="Вес" value={`${formatWeight(data.current?.weight_kg ?? null)} кг`} detail={data.previous ? `${signedWeight(data.change_from_previous_kg)} кг к прошлому` : "Последнее измерение"} />
          <MetricTile label="Цель" value={`${formatWeight(data.goal?.target_weight_kg ?? null)} кг`} detail={goalDetail(data)} tone="protein" footer={progress === null ? undefined : <ProgressBar value={progress} label="Краткий прогресс цели веса" tone="protein" />} />
          <MetricTile label="Изменение" value={`${data.period_change_kg === null ? "—" : signedWeight(data.period_change_kg)} кг`} detail="За выбранный период" tone={periodChange > 0 ? "fat" : "carbs"} />
        </div>
        <div className="weight-goal-summary">
          <div className="weight-goal-summary__title">
            <span><Goal aria-hidden="true" /></span>
            <div>
              <strong>{data.goal ? `${formatWeight(data.goal.target_weight_kg)} кг` : "Цель веса не задана"}</strong>
              <small>{data.goal?.target_date ? `Срок: ${new Intl.DateTimeFormat("ru-RU", { dateStyle: "long" }).format(new Date(`${data.goal.target_date}T12:00:00Z`))}` : "Без срока"}</small>
            </div>
            <button type="button" className="button-text" onClick={() => setGoalOpen(true)}>{data.goal ? "Изменить" : "Задать"}</button>
          </div>
          {data.goal?.progress ? (
            <div className="weight-goal-progress">
              <div><span>{data.goal.progress.achieved ? "Достигнуто" : `Осталось ${formatWeight(data.goal.progress.remaining_kg)} кг`}</span><strong>{formatWeight(data.goal.progress.percentage)}%</strong></div>
              <ProgressBar value={Number(data.goal.progress.percentage)} label="Прогресс цели веса" tone="protein" />
            </div>
          ) : data.goal ? (
            <p className="weight-goal-hint">Прогресс появится после первого измерения. Стартовый вес не подставляется автоматически.</p>
          ) : null}
        </div>
      </section>

      <section className="section-block weight-dynamics" aria-labelledby="weight-chart-title">
        <div className="section-heading section-heading--stackable">
          <div><h2 id="weight-chart-title">Динамика</h2><p>{data.points.length ? `${data.points.length} измерений` : "История измерений"}</p></div>
          <label className="range-select">
            <CalendarRange aria-hidden="true" />
            <span className="sr-only">Период графика</span>
            <select aria-label="Период графика" value={rangeChoice} onChange={(event) => { const value = event.target.value; setRangeChoice(value === "custom" ? "custom" : Number(value) as PresetRange); }}>
              {RANGE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </label>
        </div>
        {rangeChoice === "custom" && (
          <form className="custom-range" onSubmit={(event) => { event.preventDefault(); if (!customError) setAppliedCustom({ from: customFrom, to: customTo }); }}>
            <label>С <input type="date" value={customFrom} onChange={(event) => setCustomFrom(event.target.value)} /></label>
            <label>По <input type="date" value={customTo} onChange={(event) => setCustomTo(event.target.value)} /></label>
            <button type="submit" className="button-secondary" disabled={Boolean(customError)}>Показать</button>
            {customError && <p className="form-error">{customError}</p>}
          </form>
        )}
        {data.points.length ? (
          <>
            <WeightChart points={data.points} targetWeight={data.goal?.target_weight_kg ?? null} timezone={data.timezone} onSelect={setSelectedEntry} />
            <div className="weight-chart-legend" aria-label="Обозначения графика">
              <span><i className="is-actual" />Вес</span>
              <span><i className="is-average" />Среднее за 7 дней</span>
              {data.goal && <span><i className="is-target" />Цель</span>}
            </div>
          </>
        ) : (
          <div className="chart-empty">
            <div className="chart-grid" aria-hidden="true" />
            <EmptyState title="Нет измерений за этот период" description="Запишите вес, чтобы увидеть динамику." icon={Scale} action={<button type="button" className="button-primary" onClick={() => setAddOpen(true)}>Записать вес</button>} />
          </div>
        )}
      </section>

      <section className="section-block weight-history" aria-labelledby="weight-history-title">
        <div className="section-heading"><div><h2 id="weight-history-title">История</h2><p>Все измерения выбранного периода</p></div></div>
        {data.history.length ? (
          <div className="weight-history-list">
            {data.history.map((entry) => {
              const entryChange = data.current?.id === entry.id ? change : null;
              return (
                <button type="button" key={entry.id} onClick={() => setSelectedEntry(entry)}>
                  <span className="weight-history-list__date"><strong>{formatMoment(entry.measured_at, data.timezone)}</strong><small>{formatTime(entry.measured_at, data.timezone)}</small></span>
                  <span className="weight-history-list__value"><strong>{formatWeight(entry.weight_kg)} кг</strong>{entryChange !== null && data.previous && <small className={entryChange > 0 ? "is-up" : entryChange < 0 ? "is-down" : ""}>{signedWeight(data.change_from_previous_kg)} кг</small>}</span>
                  {entry.note && <span className="weight-history-list__note">{entry.note}</span>}
                  <Pencil aria-hidden="true" />
                  <ChevronRight aria-hidden="true" />
                </button>
              );
            })}
          </div>
        ) : <p className="inline-empty">Измерений в выбранном периоде нет</p>}
      </section>

      <WeightEntrySheet key={`add-${addOpen}`} open={addOpen} entry={null} timezone={data.timezone} initData={initData} authorized={authorized} onClose={() => setAddOpen(false)} onChanged={refresh} />
      <WeightEntrySheet key={selectedEntry?.id ?? "none"} open={selectedEntry !== null} entry={selectedEntry} timezone={data.timezone} initData={initData} authorized={authorized} onClose={() => setSelectedEntry(null)} onChanged={refresh} />
      <WeightGoalSheet key={`${goalOpen}-${data.goal?.id ?? "none"}`} open={goalOpen} goal={data.goal} initData={initData} authorized={authorized} onClose={() => setGoalOpen(false)} onChanged={refresh} />
    </div>
  );
}
