import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { WeightChartPoint } from "../../api/client";

interface ChartDatum extends WeightChartPoint {
  timestamp: number;
  weight: number;
  average: number | null;
}

interface ChartDotProps {
  cx?: number;
  cy?: number;
  payload?: ChartDatum;
}

interface TooltipState {
  active?: boolean;
  payload?: ReadonlyArray<{ payload?: ChartDatum }>;
}

function formatDate(value: string, timezone: string, withTime = false): string {
  return new Intl.DateTimeFormat("ru-RU", {
    timeZone: timezone,
    day: "numeric",
    month: "short",
    ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}),
  }).format(new Date(value));
}

function ChartTooltip({ state, timezone }: { state: unknown; timezone: string }) {
  const { active, payload } = state as TooltipState;
  const point = payload?.[0]?.payload;
  if (!active || !point) return null;
  return (
    <div className="weight-tooltip">
      <span>{formatDate(point.measured_at, timezone, true)}</span>
      <strong>{point.weight.toLocaleString("ru-RU", { maximumFractionDigits: 2 })} кг</strong>
      {point.average !== null && <small>Среднее: {point.average.toLocaleString("ru-RU", { maximumFractionDigits: 2 })} кг</small>}
    </div>
  );
}

function yDomain(points: ChartDatum[], target: number | null): [number, number] {
  const values = points.map((point) => point.weight);
  if (target !== null) values.push(target);
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const padding = Math.max(0.5, (maximum - minimum) * 0.12);
  return [Math.floor((minimum - padding) * 10) / 10, Math.ceil((maximum + padding) * 10) / 10];
}

interface WeightChartProps {
  points: WeightChartPoint[];
  targetWeight: string | null;
  timezone: string;
  onSelect: (entry: WeightChartPoint) => void;
}

export function WeightChart({ points, targetWeight, timezone, onSelect }: WeightChartProps) {
  const data: ChartDatum[] = points.map((point) => ({
    ...point,
    timestamp: new Date(point.measured_at).getTime(),
    weight: Number(point.weight_kg),
    average: point.moving_average_7d_kg === null ? null : Number(point.moving_average_7d_kg),
  }));
  const target = targetWeight === null ? null : Number(targetWeight);
  const domain = yDomain(data, target);
  const renderDot = (rawProps: unknown) => {
    const { cx, cy, payload } = rawProps as ChartDotProps;
    if (cx === undefined || cy === undefined || !payload) return <g />;
    const select = () => onSelect(payload);
    return (
      <circle
        cx={cx}
        cy={cy}
        r={5}
        className="weight-chart-dot"
        role="button"
        tabIndex={0}
        aria-label={`${formatDate(payload.measured_at, timezone, true)}: ${payload.weight_kg} кг`}
        onClick={select}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            select();
          }
        }}
      />
    );
  };

  return (
    <>
      <div className="weight-chart" role="group" aria-label="График изменения веса">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 12, right: 12, bottom: 8, left: 0 }}>
            <CartesianGrid stroke="var(--app-border)" strokeDasharray="3 5" vertical={false} />
            <XAxis
              dataKey="timestamp"
              type="number"
              scale="time"
              domain={["dataMin", "dataMax"]}
              tickFormatter={(value: number) => formatDate(new Date(value).toISOString(), timezone)}
              minTickGap={28}
              tickLine={false}
              axisLine={false}
              fontSize={11}
            />
            <YAxis
              domain={domain}
              width={42}
              tickFormatter={(value: number) => value.toLocaleString("ru-RU", { maximumFractionDigits: 1 })}
              tickLine={false}
              axisLine={false}
              fontSize={11}
            />
            <Tooltip content={(props) => <ChartTooltip state={props} timezone={timezone} />} cursor={{ stroke: "var(--app-muted)", strokeDasharray: "3 4" }} />
            {target !== null && <ReferenceLine y={target} stroke="var(--macro-energy)" strokeDasharray="6 5" label={{ value: "Цель", position: "insideTopRight", fill: "var(--app-muted)", fontSize: 11 }} />}
            <Line type="monotone" dataKey="average" name="Среднее за 7 дней" stroke="var(--app-muted)" strokeWidth={2} strokeDasharray="5 5" dot={false} connectNulls={false} isAnimationActive={false} />
            <Line type="monotone" dataKey="weight" name="Вес" stroke="var(--app-primary)" strokeWidth={3} dot={renderDot} activeDot={{ r: 7 }} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <p className="chart-accessible-summary">
        {points.length === 1
          ? `Одно измерение: ${points[0].weight_kg} кг, ${formatDate(points[0].measured_at, timezone, true)}.`
          : `${points.length} измерений с ${formatDate(points[0].measured_at, timezone)} по ${formatDate(points.at(-1)!.measured_at, timezone)}.`}
      </p>
    </>
  );
}
