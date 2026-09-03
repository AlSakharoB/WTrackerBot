import { ChevronLeft, ChevronRight } from "lucide-react";

import { IconButton } from "./IconButton";

interface DateSwitcherProps {
  value: Date;
  onChange: (date: Date) => void;
}

function addDays(date: Date, days: number) {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

function formatDate(date: Date) {
  const today = new Date();
  if (date.toDateString() === today.toDateString()) return "Сегодня";
  return new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "long",
  }).format(date);
}

export function DateSwitcher({ value, onChange }: DateSwitcherProps) {
  return (
    <div className="date-switcher" aria-label="Выбор даты">
      <IconButton
        label="Предыдущий день"
        icon={ChevronLeft}
        onClick={() => onChange(addDays(value, -1))}
      />
      <div className="date-switcher__value" aria-live="polite">
        <strong>{formatDate(value)}</strong>
        <span>
          {new Intl.DateTimeFormat("ru-RU", { weekday: "long" }).format(value)}
        </span>
      </div>
      <IconButton
        label="Следующий день"
        icon={ChevronRight}
        onClick={() => onChange(addDays(value, 1))}
      />
    </div>
  );
}
