export interface WeightDateRange {
  from: string;
  to: string;
}

export type GestureDirection = "pending" | "horizontal" | "vertical";

export const MIN_WEIGHT_RANGE_DAYS = 7;
export const MAX_WEIGHT_RANGE_DAYS = 365;
export const WEIGHT_RANGE_PRESETS = [7, 30, 90, 180, 365] as const;

const DAY_MS = 86_400_000;

function parseDay(value: string): number {
  return Date.parse(`${value}T00:00:00Z`);
}

function formatDay(value: number): string {
  return new Date(value).toISOString().slice(0, 10);
}

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(maximum, Math.max(minimum, value));
}

export function inclusiveDayCount(range: WeightDateRange): number {
  return Math.round((parseDay(range.to) - parseDay(range.from)) / DAY_MS) + 1;
}

export function latestWeightRange(days: number, today: string): WeightDateRange {
  const normalizedDays = clamp(Math.round(days), MIN_WEIGHT_RANGE_DAYS, MAX_WEIGHT_RANGE_DAYS);
  return {
    from: formatDay(parseDay(today) - (normalizedDays - 1) * DAY_MS),
    to: today,
  };
}

export function normalizeWeightRange(
  range: WeightDateRange,
  today: string,
): WeightDateRange {
  const rawDays = inclusiveDayCount(range);
  const days = clamp(Number.isFinite(rawDays) ? rawDays : MIN_WEIGHT_RANGE_DAYS, MIN_WEIGHT_RANGE_DAYS, MAX_WEIGHT_RANGE_DAYS);
  const latestEnd = parseDay(today);
  const requestedEnd = Math.min(parseDay(range.to), latestEnd);
  return {
    from: formatDay(requestedEnd - (days - 1) * DAY_MS),
    to: formatDay(requestedEnd),
  };
}

export function shiftWeightRange(
  range: WeightDateRange,
  days: number,
  today: string,
): WeightDateRange {
  const duration = inclusiveDayCount(range);
  const latestEnd = parseDay(today);
  const shiftedEnd = Math.min(parseDay(range.to) + Math.round(days) * DAY_MS, latestEnd);
  return {
    from: formatDay(shiftedEnd - (duration - 1) * DAY_MS),
    to: formatDay(shiftedEnd),
  };
}

export function panWeightRange(
  range: WeightDateRange,
  horizontalPixels: number,
  plotWidth: number,
  today: string,
): WeightDateRange {
  if (!Number.isFinite(plotWidth) || plotWidth <= 0) return range;
  const shiftDays = Math.round(-(horizontalPixels / plotWidth) * inclusiveDayCount(range));
  return shiftWeightRange(range, shiftDays, today);
}

export function zoomWeightRange(
  range: WeightDateRange,
  scaleFactor: number,
  midpointRatio: number,
  today: string,
): WeightDateRange {
  if (!Number.isFinite(scaleFactor) || scaleFactor <= 0) return range;
  const oldDays = inclusiveDayCount(range);
  const newDays = clamp(Math.round(oldDays / scaleFactor), MIN_WEIGHT_RANGE_DAYS, MAX_WEIGHT_RANGE_DAYS);
  const anchorRatio = clamp(midpointRatio, 0, 1);
  const anchor = parseDay(range.from) + Math.round((oldDays - 1) * anchorRatio) * DAY_MS;
  let start = anchor - Math.round((newDays - 1) * anchorRatio) * DAY_MS;
  let end = start + (newDays - 1) * DAY_MS;
  const latestEnd = parseDay(today);

  if (end > latestEnd) {
    start -= end - latestEnd;
    end = latestEnd;
  }

  return { from: formatDay(start), to: formatDay(end) };
}

export function gestureDirection(
  horizontalPixels: number,
  verticalPixels: number,
  threshold = 8,
): GestureDirection {
  const horizontal = Math.abs(horizontalPixels);
  const vertical = Math.abs(verticalPixels);
  if (Math.max(horizontal, vertical) < threshold) return "pending";
  return horizontal > vertical ? "horizontal" : "vertical";
}

export function matchingWeightPreset(days: number): number | null {
  return WEIGHT_RANGE_PRESETS.find((preset) => preset === days) ?? null;
}

export function isSameWeightRange(left: WeightDateRange, right: WeightDateRange): boolean {
  return left.from === right.from && left.to === right.to;
}

