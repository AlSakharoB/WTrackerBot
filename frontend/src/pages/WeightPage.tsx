import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CalendarRange,
  ChevronLeft,
  ChevronRight,
  Goal,
  Minus,
  Pencil,
  Plus,
  RotateCcw,
  Scale,
  TrendingDown,
  TrendingUp,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { useMemo, useState } from "react";

import { fetchWeightRange, type WeightEntry, type WeightRange } from "../api/client";
import { useMiniAppContext } from "../app/context";
import { EmptyState, ErrorState, IconButton, ProgressBar, Skeleton } from "../components/ui";
import { WeightChart } from "../components/weight/WeightChart";
import { WeightEntrySheet } from "../components/weight/WeightEntrySheet";
import { WeightGoalSheet } from "../components/weight/WeightGoalSheet";
import {
  MAX_WEIGHT_RANGE_DAYS,
  MIN_WEIGHT_RANGE_DAYS,
  WEIGHT_RANGE_PRESETS,
  inclusiveDayCount,
  latestWeightRange,
  matchingWeightPreset,
  normalizeWeightRange,
  shiftWeightRange,
  zoomWeightRange,
  type WeightDateRange,
} from "../components/weight/weightRangeController";

type PresetRange = typeof WEIGHT_RANGE_PRESETS[number];
type RangeChoice = PresetRange | "custom";

const RANGE_OPTIONS: Array<{ value: RangeChoice; label: string }> = [
  ...WEIGHT_RANGE_PRESETS.map((value) => ({ value, label: `${value} дней` })),
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

function formatRangeDate(value: string, includeYear: boolean): string {
  return new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "short",
    ...(includeYear ? { year: "numeric" } : {}),
  }).format(new Date(`${value}T12:00:00Z`));
}

function dayWord(days: number): string {
  const lastTwo = days % 100;
  const last = days % 10;
  if (lastTwo >= 11 && lastTwo <= 14) return "дней";
  if (last === 1) return "день";
  if (last >= 2 && last <= 4) return "дня";
  return "дней";
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
  if (!data.goal) return "Цель не задана";
  if (!data.current) return "Запишите текущий вес";
  if (data.goal.progress?.achieved) return "Цель достигнута";
  const distance = Math.abs(Number(data.goal.target_weight_kg) - Number(data.current.weight_kg));
  return `Осталось ${formatWeight(String(distance))} кг`;
}

function goalDirection(data: WeightRange): string | null {
  if (!data.goal) return null;
  const base = data.goal.start_weight_kg ?? data.current?.weight_kg;
  if (base === null || base === undefined) return null;
  const delta = Number(data.goal.target_weight_kg) - Number(base);
  if (delta > 0) return "Цель на набор";
  if (delta < 0) return "Цель на снижение";
  return "Целевой вес достигнут";
}

function rangeChoiceFor(range: WeightDateRange): RangeChoice {
  return (matchingWeightPreset(inclusiveDayCount(range)) ?? "custom") as RangeChoice;
}

export function WeightPage() {
  const { user, profile, initData } = useMiniAppContext();
  const queryClient = useQueryClient();
  const timezone = user?.timezone ?? Intl.DateTimeFormat().resolvedOptions().timeZone ?? "UTC";
  const today = dateInTimezone(new Date(), timezone);
  const initialRange = useMemo(() => latestWeightRange(30, today), [today]);
  const [range, setRange] = useState<WeightDateRange>(initialRange);
  const [rangeChoice, setRangeChoice] = useState<RangeChoice>(30);
  const [customFrom, setCustomFrom] = useState(initialRange.from);
  const [customTo, setCustomTo] = useState(initialRange.to);
  const [showGestureHint, setShowGestureHint] = useState(() => {
    try {
      return localStorage.getItem("miniapp:weight-gesture-used") !== "true";
    } catch {
      return true;
    }
  });
  const [addOpen, setAddOpen] = useState(false);
  const [goalOpen, setGoalOpen] = useState(false);
  const [selectedEntry, setSelectedEntry] = useState<WeightEntry | null>(null);
  const authorized = initData.length > 0;

  const validCustomDates = /^\d{4}-\d{2}-\d{2}$/.test(customFrom) && /^\d{4}-\d{2}-\d{2}$/.test(customTo);
  const customDays = validCustomDates ? inclusiveDayCount({ from: customFrom, to: customTo }) : 0;
  const customError = !validCustomDates
    ? "Укажите обе даты"
    : customFrom > customTo
      ? "Начальная дата должна быть раньше конечной"
      : customTo > today
        ? "Конечная дата не может быть в будущем"
        : customDays < MIN_WEIGHT_RANGE_DAYS
          ? `Период не может быть короче ${MIN_WEIGHT_RANGE_DAYS} дней`
          : customDays > MAX_WEIGHT_RANGE_DAYS
            ? `Период не может быть больше ${MAX_WEIGHT_RANGE_DAYS} дней`
            : undefined;
  const weightQuery = useQuery({
    queryKey: ["weight", range.from, range.to],
    queryFn: () => fetchWeightRange(initData, range.from, range.to),
    enabled: authorized,
    retry: false,
    placeholderData: (previous) => previous,
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
  const commitRange = (next: WeightDateRange, gesture = false) => {
    const normalized = normalizeWeightRange(next, today);
    if (gesture && showGestureHint) {
      setShowGestureHint(false);
      try {
        localStorage.setItem("miniapp:weight-gesture-used", "true");
      } catch {
        // Storage may be unavailable in a restricted WebView.
      }
    }
    setRangeChoice(rangeChoiceFor(normalized));
    setRange(normalized);
    setCustomFrom(normalized.from);
    setCustomTo(normalized.to);
  };
  const days = inclusiveDayCount(range);
  const isCurrentRange = range.to === today;
  const rangeDataReady = data.date_from === range.from && data.date_to === range.to;
  const points = rangeDataReady ? data.points : [];
  const history = rangeDataReady ? data.history : [];
  const change = Number(data.change_from_previous_kg ?? 0);
  const ChangeIcon = change < 0 ? TrendingDown : change > 0 ? TrendingUp : Minus;
  const rangeYearsDiffer = range.from.slice(0, 4) !== range.to.slice(0, 4);

  return (
    <div className="page page--weight">
      <section className="weight-overview" aria-labelledby="weight-summary-title">
        <div className="section-heading weight-heading">
          <div>
            <h1 id="weight-summary-title">Текущий вес</h1>
            <p>{data.current ? formatMoment(data.current.measured_at, data.timezone, true) : "Нет измерений"}</p>
          </div>
          <button className="button-primary button-with-icon" type="button" onClick={() => setAddOpen(true)}>
            <Plus aria-hidden="true" size={18} /> Записать
          </button>
        </div>

        <div className="weight-current-status">
          <div className="weight-current-value">
            <Scale aria-hidden="true" />
            <strong>{formatWeight(data.current?.weight_kg ?? null)} <small>кг</small></strong>
          </div>
          <div className={`weight-change ${change < 0 ? "is-down" : change > 0 ? "is-up" : "is-flat"}`}>
            <ChangeIcon aria-hidden="true" />
            <strong>{data.previous ? `${signedWeight(data.change_from_previous_kg)} кг` : "Нет сравнения"}</strong>
            <span>{data.previous ? "к предыдущему" : "первое измерение"}</span>
          </div>
        </div>

        <div className="weight-goal-summary">
          <div className="weight-goal-summary__title">
            <span><Goal aria-hidden="true" /></span>
            <div>
              <small>Цель</small>
              <strong>{data.goal ? `${formatWeight(data.goal.target_weight_kg)} кг` : "Не задана"}</strong>
              <span>{[goalDetail(data), goalDirection(data)].filter(Boolean).join(" · ")}</span>
            </div>
            <button type="button" className="button-text" onClick={() => setGoalOpen(true)}>{data.goal ? "Изменить" : "Задать"}</button>
          </div>
          {data.goal?.progress ? (
            <div className="weight-goal-progress">
              <div><span>{data.goal.progress.achieved ? "Достигнуто" : `Пройдено ${formatWeight(data.goal.progress.completed_kg)} кг`}</span><strong>{formatWeight(data.goal.progress.percentage)}%</strong></div>
              <ProgressBar value={Number(data.goal.progress.percentage)} label="Прогресс цели веса" tone="protein" />
              {data.goal.target_date && <small>Желаемая дата: {new Intl.DateTimeFormat("ru-RU", { dateStyle: "long" }).format(new Date(`${data.goal.target_date}T12:00:00Z`))}</small>}
            </div>
          ) : data.goal ? (
            <p className="weight-goal-hint">Прогресс появится после первого измерения. Стартовый вес не подставляется автоматически.</p>
          ) : null}
        </div>
      </section>

      <section className="section-block weight-dynamics" aria-labelledby="weight-chart-title">
        <div className="section-heading section-heading--stackable">
          <div>
            <h2 id="weight-chart-title">Динамика</h2>
            <p>{rangeDataReady && data.period_change_kg !== null ? `${signedWeight(data.period_change_kg)} кг за период` : weightQuery.isFetching ? "Обновляем данные" : "Изменение за период"}</p>
          </div>
          <label className="range-select">
            <CalendarRange aria-hidden="true" />
            <span className="sr-only">Период графика</span>
            <select
              aria-label="Период графика"
              value={rangeChoice}
              onChange={(event) => {
                const value = event.target.value;
                if (value === "custom") {
                  setRangeChoice("custom");
                  setCustomFrom(range.from);
                  setCustomTo(range.to);
                  return;
                }
                const preset = Number(value) as PresetRange;
                commitRange(latestWeightRange(preset, today));
              }}
            >
              {RANGE_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </label>
        </div>
        {rangeChoice === "custom" && (
          <form
            className="custom-range"
            onSubmit={(event) => {
              event.preventDefault();
              if (!customError) commitRange({ from: customFrom, to: customTo });
            }}
          >
            <label>С <input type="date" max={today} value={customFrom} onChange={(event) => setCustomFrom(event.target.value)} /></label>
            <label>По <input type="date" max={today} value={customTo} onChange={(event) => setCustomTo(event.target.value)} /></label>
            <button type="submit" className="button-secondary" disabled={Boolean(customError)}>Показать</button>
            {customError && <p className="form-error">{customError}</p>}
          </form>
        )}

        <div className="weight-window">
          <div className="weight-window__summary" aria-live="polite">
            <span>{formatRangeDate(range.from, rangeYearsDiffer)} — {formatRangeDate(range.to, true)}</span>
            <strong>{days} {dayWord(days)}</strong>
          </div>
          <div className="weight-window__controls" role="group" aria-label="Управление периодом графика">
            <IconButton label="Предыдущий период" icon={ChevronLeft} onClick={() => commitRange(shiftWeightRange(range, -days, today))} />
            <IconButton label="Следующий период" icon={ChevronRight} disabled={isCurrentRange} onClick={() => commitRange(shiftWeightRange(range, days, today))} />
            <IconButton label="Приблизить график" icon={ZoomIn} disabled={days <= MIN_WEIGHT_RANGE_DAYS} onClick={() => commitRange(zoomWeightRange(range, 1.5, 0.5, today))} />
            <IconButton label="Отдалить график" icon={ZoomOut} disabled={days >= MAX_WEIGHT_RANGE_DAYS} onClick={() => commitRange(zoomWeightRange(range, 1 / 1.5, 0.5, today))} />
            <IconButton label="Вернуться к текущему периоду" icon={RotateCcw} disabled={isCurrentRange} onClick={() => commitRange(latestWeightRange(days, today))} />
          </div>
        </div>
        {showGestureHint && <p className="weight-gesture-hint">График можно двигать одним пальцем и масштабировать двумя</p>}

        {points.length ? (
          <>
            <WeightChart
              key={`${range.from}-${range.to}`}
              points={points}
              targetWeight={data.goal?.target_weight_kg ?? null}
              timezone={data.timezone}
              range={range}
              today={today}
              isLoading={weightQuery.isFetching}
              onRangeCommit={(next) => commitRange(next, true)}
              onSelect={setSelectedEntry}
            />
            <div className="weight-chart-legend" aria-label="Обозначения графика">
              <span><i className="is-actual" />Вес</span>
              <span><i className="is-average" />Среднее за 7 дней</span>
              {data.goal && <span><i className="is-target" />Цель</span>}
            </div>
          </>
        ) : !rangeDataReady && weightQuery.isFetching ? (
          <div className="weight-chart-placeholder" role="status" aria-live="polite">
            <div className="chart-grid" aria-hidden="true" />
            <span>Загружаем период</span>
          </div>
        ) : (
          <div className="chart-empty">
            <div className="chart-grid" aria-hidden="true" />
            <EmptyState
              title="Нет измерений за этот период"
              description={isCurrentRange ? "Запишите вес, чтобы увидеть динамику." : "В этом временном окне записей нет."}
              icon={Scale}
              action={isCurrentRange
                ? <button type="button" className="button-primary" onClick={() => setAddOpen(true)}>Записать вес</button>
                : <button type="button" className="button-secondary" onClick={() => commitRange(latestWeightRange(days, today))}>К текущему периоду</button>}
            />
          </div>
        )}
      </section>

      <section className="section-block weight-history" aria-labelledby="weight-history-title">
        <div className="section-heading">
          <div><h2 id="weight-history-title">История</h2><p>{history.length ? `${history.length} записей в периоде` : "Все измерения выбранного периода"}</p></div>
        </div>
        {history.length ? (
          <div className="weight-history-list">
            {history.map((entry, index) => {
              const olderEntry = history[index + 1];
              const entryChange = olderEntry ? Number(entry.weight_kg) - Number(olderEntry.weight_kg) : null;
              return (
                <button type="button" key={entry.id} onClick={() => setSelectedEntry(entry)} aria-label={`Изменить измерение ${formatMoment(entry.measured_at, data.timezone)}: ${formatWeight(entry.weight_kg)} кг`}>
                  <span className="weight-history-list__date"><strong>{formatMoment(entry.measured_at, data.timezone)}</strong><small>{formatTime(entry.measured_at, data.timezone)}</small></span>
                  <span className="weight-history-list__value"><strong>{formatWeight(entry.weight_kg)} кг</strong>{entryChange !== null && <small className={entryChange > 0 ? "is-up" : entryChange < 0 ? "is-down" : ""}>{signedWeight(String(entryChange))} кг</small>}</span>
                  {entry.note && <span className="weight-history-list__note">{entry.note}</span>}
                  <Pencil aria-hidden="true" />
                </button>
              );
            })}
          </div>
        ) : weightQuery.isFetching ? <Skeleton lines={3} /> : <p className="inline-empty">Измерений в выбранном периоде нет</p>}
      </section>

      <WeightEntrySheet key={`add-${addOpen}`} open={addOpen} entry={null} timezone={data.timezone} initData={initData} authorized={authorized} confirmDeletions={profile.confirm_deletions} onClose={() => setAddOpen(false)} onChanged={refresh} />
      <WeightEntrySheet key={selectedEntry?.id ?? "none"} open={selectedEntry !== null} entry={selectedEntry} timezone={data.timezone} initData={initData} authorized={authorized} confirmDeletions={profile.confirm_deletions} onClose={() => setSelectedEntry(null)} onChanged={refresh} />
      <WeightGoalSheet key={`${goalOpen}-${data.goal?.id ?? "none"}`} open={goalOpen} goal={data.goal} initData={initData} authorized={authorized} confirmDeletions={profile.confirm_deletions} onClose={() => setGoalOpen(false)} onChanged={refresh} />
    </div>
  );
}
