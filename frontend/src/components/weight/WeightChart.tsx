import { Pencil } from "lucide-react";
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";
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
import {
  gestureDirection,
  inclusiveDayCount,
  isSameWeightRange,
  panWeightRange,
  zoomWeightRange,
  type GestureDirection,
  type WeightDateRange,
} from "./weightRangeController";

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

interface ActivePointer {
  x: number;
  y: number;
}

interface ActiveGesture {
  kind: GestureDirection | "pinch";
  initialRange: WeightDateRange;
  pointerId: number;
  startX: number;
  startY: number;
  pinchDistance: number;
  pinchMidpointRatio: number;
  plotWidth: number;
}

function formatDate(value: string, timezone: string, withTime = false): string {
  return new Intl.DateTimeFormat("ru-RU", {
    timeZone: timezone,
    day: "numeric",
    month: "short",
    ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}),
  }).format(new Date(value));
}

function timestampInTimezone(value: string, timezone: string): number {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(value));
  const get = (type: Intl.DateTimeFormatPartTypes) => Number(parts.find((part) => part.type === type)?.value ?? 0);
  return Date.UTC(get("year"), get("month") - 1, get("day"), get("hour"), get("minute"), get("second"));
}

function chartBoundary(value: string, end = false): number {
  return Date.parse(`${value}T${end ? "23:59:59.999" : "00:00:00.000"}Z`);
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
  const values = points.flatMap((point) => point.average === null ? [point.weight] : [point.weight, point.average]);
  if (target !== null) values.push(target);
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const padding = Math.max(0.5, (maximum - minimum) * 0.12);
  return [Math.floor((minimum - padding) * 10) / 10, Math.ceil((maximum + padding) * 10) / 10];
}

function pointerDistance(first: ActivePointer, second: ActivePointer): number {
  return Math.hypot(second.x - first.x, second.y - first.y);
}

function accessibleSummary(points: ChartDatum[], timezone: string): string {
  if (points.length === 1) {
    return `Одно измерение: ${points[0].weight_kg} кг, ${formatDate(points[0].measured_at, timezone, true)}.`;
  }
  const first = points[0];
  const last = points.at(-1)!;
  const change = last.weight - first.weight;
  const direction = change < 0 ? "снижение" : change > 0 ? "увеличение" : "без изменения";
  return `${points.length} измерений с ${formatDate(first.measured_at, timezone)} по ${formatDate(last.measured_at, timezone)}. ${direction}: ${Math.abs(change).toLocaleString("ru-RU", { maximumFractionDigits: 2 })} кг.`;
}

interface WeightChartProps {
  points: WeightChartPoint[];
  targetWeight: string | null;
  timezone: string;
  range: WeightDateRange;
  today: string;
  isLoading?: boolean;
  onRangeCommit: (range: WeightDateRange) => void;
  onSelect: (entry: WeightChartPoint) => void;
}

export function WeightChart({
  points,
  targetWeight,
  timezone,
  range,
  today,
  isLoading = false,
  onRangeCommit,
  onSelect,
}: WeightChartProps) {
  const data = useMemo<ChartDatum[]>(() => points
    .map((point) => ({
      ...point,
      timestamp: timestampInTimezone(point.measured_at, timezone),
      weight: Number(point.weight_kg),
      average: point.moving_average_7d_kg === null ? null : Number(point.moving_average_7d_kg),
    }))
    .sort((left, right) => left.timestamp - right.timestamp), [points, timezone]);
  const target = targetWeight === null ? null : Number(targetWeight);
  const domain = useMemo(() => yDomain(data, target), [data, target]);
  const [previewRange, setPreviewRange] = useState(range);
  const [gestureActive, setGestureActive] = useState(false);
  const [selectedPoint, setSelectedPoint] = useState<ChartDatum | null>(null);
  const plotRef = useRef<HTMLDivElement | null>(null);
  const pointersRef = useRef(new Map<number, ActivePointer>());
  const gestureRef = useRef<ActiveGesture | null>(null);
  const previewRef = useRef(range);
  const previewFrameRef = useRef<number | null>(null);
  const suppressClickRef = useRef(false);
  const selectedTooltipRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!gestureRef.current) {
      previewRef.current = range;
      setPreviewRange((current) => isSameWeightRange(current, range) ? current : range);
    }
  }, [range]);

  useEffect(() => {
    const plot = plotRef.current;
    const pointers = pointersRef.current;
    return () => {
      if (previewFrameRef.current !== null) {
        if (window.cancelAnimationFrame) window.cancelAnimationFrame(previewFrameRef.current);
        else window.clearTimeout(previewFrameRef.current);
      }
      if (plot) {
        for (const pointerId of pointers.keys()) {
          if (plot.hasPointerCapture?.(pointerId)) plot.releasePointerCapture(pointerId);
        }
      }
      pointers.clear();
      gestureRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!selectedPoint) return;
    const dismissSelectedPoint = (event: PointerEvent) => {
      const target = event.target;
      if (target instanceof Node && selectedTooltipRef.current?.contains(target)) return;
      setSelectedPoint(null);
    };
    document.addEventListener("pointerdown", dismissSelectedPoint);
    return () => document.removeEventListener("pointerdown", dismissSelectedPoint);
  }, [selectedPoint]);

  const cancelPreviewFrame = () => {
    if (previewFrameRef.current === null) return;
    if (window.cancelAnimationFrame) window.cancelAnimationFrame(previewFrameRef.current);
    else window.clearTimeout(previewFrameRef.current);
    previewFrameRef.current = null;
  };

  const queuePreview = (next: WeightDateRange) => {
    previewRef.current = next;
    if (previewFrameRef.current !== null) return;
    const apply = () => {
      previewFrameRef.current = null;
      setPreviewRange(previewRef.current);
    };
    previewFrameRef.current = window.requestAnimationFrame
      ? window.requestAnimationFrame(apply)
      : window.setTimeout(apply, 16);
  };

  const finishGesture = (commit: boolean) => {
    const gesture = gestureRef.current;
    cancelPreviewFrame();
    if (commit && gesture && (gesture.kind === "horizontal" || gesture.kind === "pinch")) {
      suppressClickRef.current = true;
      setSelectedPoint(null);
      setPreviewRange(previewRef.current);
      if (!isSameWeightRange(previewRef.current, range)) onRangeCommit(previewRef.current);
    } else if (!commit) {
      previewRef.current = range;
      setPreviewRange(range);
    }
    const plot = plotRef.current;
    if (plot) {
      for (const pointerId of pointersRef.current.keys()) {
        if (plot.hasPointerCapture?.(pointerId)) plot.releasePointerCapture(pointerId);
      }
    }
    pointersRef.current.clear();
    gestureRef.current = null;
    setGestureActive(false);
  };

  const handlePointerDown = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (event.button !== 0 && event.pointerType === "mouse") return;
    pointersRef.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
    event.currentTarget.setPointerCapture?.(event.pointerId);
    const bounds = event.currentTarget.getBoundingClientRect();

    if (pointersRef.current.size === 1) {
      gestureRef.current = {
        kind: "pending",
        initialRange: range,
        pointerId: event.pointerId,
        startX: event.clientX,
        startY: event.clientY,
        pinchDistance: 0,
        pinchMidpointRatio: 0.5,
        plotWidth: Math.max(bounds.width, 1),
      };
      suppressClickRef.current = false;
      return;
    }

    const [first, second] = [...pointersRef.current.values()];
    gestureRef.current = {
      kind: "pinch",
      initialRange: previewRef.current,
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      pinchDistance: Math.max(pointerDistance(first, second), 1),
      pinchMidpointRatio: Math.min(1, Math.max(0, ((first.x + second.x) / 2 - bounds.left) / Math.max(bounds.width, 1))),
      plotWidth: Math.max(bounds.width, 1),
    };
    setGestureActive(true);
    event.preventDefault();
  };

  const handlePointerMove = (event: ReactPointerEvent<HTMLDivElement>) => {
    if (!pointersRef.current.has(event.pointerId)) return;
    pointersRef.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
    const gesture = gestureRef.current;
    if (!gesture) return;

    if (gesture.kind === "pinch" && pointersRef.current.size >= 2) {
      const [first, second] = [...pointersRef.current.values()];
      const scale = pointerDistance(first, second) / gesture.pinchDistance;
      queuePreview(zoomWeightRange(gesture.initialRange, scale, gesture.pinchMidpointRatio, today));
      event.preventDefault();
      return;
    }

    if (event.pointerId !== gesture.pointerId || pointersRef.current.size !== 1) return;
    const deltaX = event.clientX - gesture.startX;
    const deltaY = event.clientY - gesture.startY;
    if (gesture.kind === "pending") {
      gesture.kind = gestureDirection(deltaX, deltaY);
      if (gesture.kind === "horizontal") setGestureActive(true);
    }
    if (gesture.kind === "horizontal") {
      queuePreview(panWeightRange(gesture.initialRange, deltaX, gesture.plotWidth, today));
      event.preventDefault();
    }
  };

  const handlePointClick = (event: ReactMouseEvent<SVGGElement>, point: ChartDatum) => {
    event.stopPropagation();
    if (suppressClickRef.current) {
      suppressClickRef.current = false;
      return;
    }
    setSelectedPoint(point);
  };

  const renderDot = (rawProps: unknown) => {
    const { cx, cy, payload } = rawProps as ChartDotProps;
    if (cx === undefined || cy === undefined || !payload) return <g />;
    return (
      <g
        className="weight-chart-point"
        role="button"
        tabIndex={0}
        aria-label={`${formatDate(payload.measured_at, timezone, true)}: ${payload.weight_kg} кг`}
        onClick={(event) => handlePointClick(event, payload)}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            setSelectedPoint(payload);
          }
        }}
      >
        <circle cx={cx} cy={cy} r={23} className="weight-chart-hit-area" />
        <circle cx={cx} cy={cy} r={5} className="weight-chart-dot" />
      </g>
    );
  };
  const days = inclusiveDayCount(previewRange);
  const tickCount = days <= 14 ? 4 : days <= 90 ? 5 : 6;

  return (
    <>
      <div
        ref={plotRef}
        className={`weight-chart ${gestureActive ? "is-gesturing" : ""}`}
        role="group"
        aria-label="Интерактивный график изменения веса"
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={() => finishGesture(true)}
        onPointerCancel={() => finishGesture(false)}
      >
        <div className="weight-chart__canvas">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 16, right: 12, bottom: 8, left: 0 }}>
              <CartesianGrid stroke="var(--color-border)" strokeDasharray="3 5" vertical={false} />
              <XAxis
                dataKey="timestamp"
                type="number"
                scale="time"
                domain={[chartBoundary(previewRange.from), chartBoundary(previewRange.to, true)]}
                tickCount={tickCount}
                tickFormatter={(value: number) => formatDate(new Date(value).toISOString(), "UTC")}
                minTickGap={22}
                tickLine={false}
                axisLine={false}
                fontSize={11}
                allowDataOverflow
              />
              <YAxis
                domain={domain}
                width={42}
                tickCount={5}
                tickFormatter={(value: number) => value.toLocaleString("ru-RU", { maximumFractionDigits: 1 })}
                tickLine={false}
                axisLine={false}
                fontSize={11}
              />
              {!selectedPoint && <Tooltip content={(props) => <ChartTooltip state={props} timezone={timezone} />} cursor={{ stroke: "var(--color-text-secondary)", strokeDasharray: "3 4" }} />}
              {target !== null && <ReferenceLine y={target} stroke="var(--color-energy)" strokeDasharray="6 5" label={{ value: "Цель", position: "insideTopRight", fill: "var(--color-text-secondary)", fontSize: 11 }} />}
              <Line type="monotone" dataKey="average" name="Среднее за 7 дней" stroke="var(--color-text-secondary)" strokeWidth={2} strokeDasharray="5 5" dot={false} connectNulls={false} isAnimationActive={false} />
              <Line type="monotone" dataKey="weight" name="Вес" stroke="var(--color-action-primary)" strokeWidth={3} dot={renderDot} activeDot={{ r: 7 }} isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
        {selectedPoint && (
          <div ref={selectedTooltipRef} className="weight-tooltip weight-tooltip--selected" role="status">
            <span>{formatDate(selectedPoint.measured_at, timezone, true)}</span>
            <strong>{selectedPoint.weight.toLocaleString("ru-RU", { maximumFractionDigits: 2 })} кг</strong>
            {selectedPoint.average !== null && <small>Среднее: {selectedPoint.average.toLocaleString("ru-RU", { maximumFractionDigits: 2 })} кг</small>}
            <button type="button" onClick={() => { const point = selectedPoint; setSelectedPoint(null); onSelect(point); }}><Pencil aria-hidden="true" /> Изменить</button>
          </div>
        )}
        {isLoading && <div className="weight-chart__loading" role="status" aria-live="polite"><span />Обновляем период</div>}
      </div>
      <p className="chart-accessible-summary">{accessibleSummary(data, timezone)}</p>
    </>
  );
}
