import { useQuery } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";

import { fetchRationWeek, type RationDay } from "../../api/client";
import { DateSwitcher } from "../ui";
import { shiftWeek, weekDates } from "./weekDates";

interface RationWeekProps {
  value: string;
  today: string;
  initData: string;
  day?: RationDay;
  onChange: (value: string) => void;
}

export function RationWeek({ value, today, initData, day, onChange }: RationWeekProps) {
  const dates = weekDates(value);
  const reducedMotion = useReducedMotion();
  const week = useQuery({
    queryKey: ["ration-week", dates[0]],
    // Cache the summary even if the user leaves the week before it finishes.
    queryFn: () => fetchRationWeek(initData, dates[0]),
    enabled: Boolean(initData),
    staleTime: 60_000,
    retry: false,
  });
  return <div className="ration-week">
    <motion.div className="ration-week__swipe" drag="x" dragConstraints={{ left: 0, right: 0 }} dragElastic={reducedMotion ? 0 : 0.12} dragMomentum={false}
      onDragEnd={(event, info) => {
        if (event.type === "pointercancel") return;
        if (Math.abs(info.offset.x) >= 48 && Math.abs(info.offset.x) > Math.abs(info.offset.y) * 1.3) {
          onChange(shiftWeek(value, info.offset.x < 0 ? 1 : -1));
        }
      }}
      onKeyDown={(event) => {
        if (event.altKey || event.ctrlKey || event.metaKey || !["ArrowLeft", "ArrowRight", "PageUp", "PageDown"].includes(event.key)) return;
        event.preventDefault();
        onChange(shiftWeek(value, event.key === "ArrowLeft" || event.key === "PageUp" ? -1 : 1));
      }}>
      <DateSwitcher value={value} today={today} isFuture={value > today} onChange={onChange} />
      <nav className="ration-week__days" aria-label="Дни недели" aria-keyshortcuts="ArrowLeft ArrowRight PageUp PageDown">
        {dates.map((date) => {
          const item = date === day?.date ? { entry_count: day.entry_count, energy_kcal: day.totals.energy_kcal } : week.data?.days.find((item) => item.date === date);
          const localDate = new Date(`${date}T12:00:00Z`);
          const label = new Intl.DateTimeFormat("ru-RU", { timeZone: "UTC", day: "numeric", month: "long", weekday: "long" }).format(localDate);
          const activity = item ? `${item.entry_count} записей, ${Number(item.energy_kcal).toLocaleString("ru-RU", { maximumFractionDigits: 0 })} ккал` : "данные ещё не загружены";
          return <button key={localDate.getUTCDay()} type="button" className={`${date === value ? "is-selected" : ""} ${date === today ? "is-today" : ""}`} aria-pressed={date === value} aria-current={date === today ? "date" : undefined} aria-label={`${label}${date === today ? ", сегодня" : ""}. ${activity}`} onClick={() => onChange(date)}>
            <span>{new Intl.DateTimeFormat("ru-RU", { timeZone: "UTC", weekday: "short" }).format(localDate)}</span>
            <strong>{localDate.getUTCDate()}</strong>
            <i className={`ration-week__activity ${item ? item.entry_count > 0 ? "has-entries" : "is-empty" : "is-unknown"}`} aria-hidden="true" />
          </button>;
        })}
      </nav>
    </motion.div>
    {week.isError && <button className="ration-week__retry button-text button-with-icon" type="button" onClick={() => void week.refetch()}><RefreshCw aria-hidden="true" />Обновить данные недели</button>}
  </div>;
}
