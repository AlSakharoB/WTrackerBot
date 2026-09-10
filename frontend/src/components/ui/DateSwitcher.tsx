import { CalendarDays, ChevronLeft, ChevronRight } from "lucide-react";

import { IconButton } from "./IconButton";

interface DateSwitcherProps {
  value: string;
  today: string;
  isFuture?: boolean;
  onChange: (date: string) => void;
}

function calendarDate(value: string): Date {
  return new Date(`${value}T12:00:00`);
}

function addDays(value: string, days: number): string {
  const next = calendarDate(value);
  next.setDate(next.getDate() + days);
  const year = next.getFullYear();
  const month = String(next.getMonth() + 1).padStart(2, "0");
  const day = String(next.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function formatDate(value: string, today: string): string {
  if (value === today) return "Сегодня";
  return new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "long",
  }).format(calendarDate(value));
}

export function DateSwitcher({
  value,
  today,
  isFuture = false,
  onChange,
}: DateSwitcherProps) {
  const isToday = value === today;
  return (
    <div className="date-switcher" aria-label="Выбор даты">
      <IconButton
        label="Предыдущий день"
        icon={ChevronLeft}
        onClick={() => onChange(addDays(value, -1))}
      />
      <button
        type="button"
        className="date-switcher__value"
        aria-live="polite"
        disabled={isToday}
        title={isToday ? undefined : "Вернуться к сегодняшнему дню"}
        onClick={() => onChange(today)}
      >
        <strong>{formatDate(value, today)}</strong>
        <span>
          {new Intl.DateTimeFormat("ru-RU", { weekday: "long" }).format(
            calendarDate(value),
          )}
        </span>
        {isFuture && (
          <small><CalendarDays aria-hidden="true" /> Будущая дата</small>
        )}
      </button>
      <IconButton
        label="Следующий день"
        icon={ChevronRight}
        onClick={() => onChange(addDays(value, 1))}
      />
    </div>
  );
}
