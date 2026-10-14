import { CalendarDays } from "lucide-react";

interface DateSwitcherProps {
  value: string;
  today: string;
  isFuture?: boolean;
  onChange: (date: string) => void;
}

function calendarDate(value: string): Date {
  return new Date(`${value}T12:00:00`);
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
    </div>
  );
}
