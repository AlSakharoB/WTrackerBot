import {
  closestCenter, DndContext, DragOverlay, KeyboardSensor, MouseSensor, pointerWithin,
  TouchSensor, useDraggable, useDroppable, useSensor, useSensors,
  type KeyboardCoordinateGetter,
} from "@dnd-kit/core";
import { Apple, CookingPot, EllipsisVertical, MoonStar, Plus, Salad, Sun, Sunrise, Utensils } from "lucide-react";
import { useReducedMotion } from "motion/react";
import { useState, type ElementType } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";

import type { MealType, NumberFormat, RationEntry, RationMeal } from "../../api/client";
import { SwipeableRow } from "../ui";
import { LONG_PRESS_MS } from "../ui/SwipeableRow";

const MEAL_ICONS: Record<MealType, ElementType> = {
  breakfast: Sunrise, lunch: Sun, dinner: MoonStar, snack: Apple, other: Utensils,
};
const keyboardCoordinates: KeyboardCoordinateGetter = (event, { context, currentCoordinates }) => {
  const direction = ["ArrowDown", "ArrowRight"].includes(event.code) ? 1
    : ["ArrowUp", "ArrowLeft"].includes(event.code) ? -1 : 0;
  if (!direction) return;
  event.preventDefault();
  const rect = context.collisionRect;
  if (!rect) return;
  const center = rect.top + rect.height / 2;
  const targets = [...context.droppableRects.values()]
    .filter((target) => direction > 0 ? target.top + target.height / 2 > center + 1 : target.top + target.height / 2 < center - 1)
    .sort((a, b) => direction * (a.top + a.height / 2 - b.top - b.height / 2));
  const target = targets[0];
  return target ? {
    x: currentCoordinates.x + target.left + target.width / 2 - rect.left - rect.width / 2,
    y: currentCoordinates.y + target.top + target.height / 2 - center,
  } : undefined;
};

interface RationMealsProps {
  meals: RationMeal[];
  date: string;
  format: NumberFormat;
  formatValue: (value: string | number, format: NumberFormat) => string;
  disabled: boolean;
  onSelectEntry: (entry: RationEntry) => void;
  onDeleteEntry: (entry: RationEntry) => void;
  onMoveEntry: (entry: RationEntry, meal: MealType) => void;
  onPickUp?: () => void;
}

function EntrySummary({ entry, format, formatValue }: Pick<RationMealsProps, "format" | "formatValue"> & { entry: RationEntry }) {
  return <>
    <span className="meal-entry__type">{entry.type === "dish" ? <CookingPot aria-hidden="true" /> : <Salad aria-hidden="true" />}</span>
    <span className="meal-entry__copy"><strong>{entry.source_name}</strong><small>{formatValue(entry.grams, format)} г{!entry.source_available && " · Источник удалён"}</small></span>
    <span className="meal-entry__energy">{formatValue(entry.nutrition.energy_kcal, format)} <small>ккал</small></span>
  </>;
}

function EntryRow({ entry, active, swiped, setSwiped, ...props }: RationMealsProps & {
  entry: RationEntry; active: boolean; swiped: string | null; setSwiped: (id: string | null) => void;
}) {
  const { attributes, listeners, setNodeRef, setActivatorNodeRef, isDragging } = useDraggable({ id: entry.id, data: { entry }, disabled: props.disabled || swiped === entry.id, attributes: { roleDescription: "Переносимая запись" } });
  return (
    <div ref={setNodeRef} className={`meal-entry-source ${isDragging ? "is-dragging" : ""}`} data-entry-id={entry.id}>
      <SwipeableRow label={entry.source_name} open={swiped === entry.id} onOpenChange={(open) => setSwiped(open ? entry.id : null)} disabled={props.disabled || active} layoutDisabled={active} onDelete={() => props.onDeleteEntry(entry)}>
        <div className="meal-entry">
          <button ref={setActivatorNodeRef} type="button" disabled={props.disabled} className="meal-entry__main" {...attributes} {...listeners} aria-label={`Открыть запись ${entry.source_name}`} onClick={() => props.onSelectEntry(entry)}>
            <EntrySummary entry={entry} format={props.format} formatValue={props.formatValue} />
          </button>
          <button type="button" data-row-action disabled={props.disabled} className="icon-button icon-button--small" aria-label={`Действия с записью ${entry.source_name}`} onClick={() => props.onSelectEntry(entry)}><EllipsisVertical aria-hidden="true" /></button>
        </div>
      </SwipeableRow>
    </div>
  );
}

function MealSection({ meal, active, swiped, setSwiped, ...props }: RationMealsProps & {
  meal: RationMeal; active: RationEntry | null; swiped: string | null; setSwiped: (id: string | null) => void;
}) {
  const { setNodeRef, isOver } = useDroppable({ id: meal.type, disabled: props.disabled });
  const Icon = MEAL_ICONS[meal.type];
  const addTarget = `/ration/add?date=${props.date}&meal=${meal.type}`;
  return (
    <article ref={setNodeRef} data-meal={meal.type} className={`meal-section ${active ? "is-drop-zone" : ""} ${isOver && active?.meal_type !== meal.type ? "is-drop-target" : ""}`}>
      <header>
        <span className={`meal-icon meal-icon--${meal.type}`}><Icon aria-hidden="true" /></span>
        <div><h3>{meal.label}</h3><p>{props.formatValue(meal.totals.energy_kcal, props.format)} ккал · Б {props.formatValue(meal.totals.protein_g, props.format)} · Ж {props.formatValue(meal.totals.fat_g, props.format)} · У {props.formatValue(meal.totals.carbs_g, props.format)}</p></div>
        <Link className="icon-link" to={addTarget} aria-label={`Добавить в ${meal.label.toLowerCase()}`} title="Добавить запись"><Plus aria-hidden="true" /></Link>
      </header>
      {meal.entries.length === 0 ? <Link className="meal-empty" to={addTarget}><span>Пока ничего не добавлено</span><strong>Добавить еду</strong></Link> : (
        <div className="meal-entries">{meal.entries.map((entry) => <EntryRow key={entry.id} {...props} entry={entry} active={Boolean(active)} swiped={swiped} setSwiped={setSwiped} />)}</div>
      )}
    </article>
  );
}

export function RationMeals(props: RationMealsProps) {
  const meals: RationMeal[] = props.meals.some((meal) => meal.type === "other") ? props.meals : [...props.meals, {
    type: "other", label: "Другое", entries: [], totals: { energy_kcal: "0", protein_g: "0", fat_g: "0", carbs_g: "0" },
  }];
  const [active, setActive] = useState<RationEntry | null>(null);
  const [swiped, setSwiped] = useState<string | null>(null);
  const reducedMotion = useReducedMotion();
  const sensors = useSensors(
    useSensor(MouseSensor, { activationConstraint: { delay: LONG_PRESS_MS, tolerance: 8 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: LONG_PRESS_MS, tolerance: 8 } }),
    useSensor(KeyboardSensor, { coordinateGetter: keyboardCoordinates, scrollBehavior: "auto", keyboardCodes: { start: ["Space"], end: ["Space", "Enter"], cancel: ["Escape"] } }),
  );
  return (
    <DndContext
      sensors={sensors}
      collisionDetection={(args) => args.pointerCoordinates ? pointerWithin(args) : closestCenter(args)}
      onDragStart={({ active: source }) => { setActive(source.data.current?.entry ?? null); setSwiped(null); props.onPickUp?.(); }}
      onDragCancel={() => setActive(null)}
      onDragEnd={({ over }) => {
        if (active && over && over.id !== active.meal_type && meals.some((meal) => meal.type === over.id)) props.onMoveEntry(active, over.id as MealType);
        setActive(null);
      }}
      accessibility={{
        screenReaderInstructions: { draggable: "Для переноса нажмите пробел. Стрелками выберите приём пищи. Пробел подтверждает перенос, Escape отменяет." },
        announcements: {
          onDragStart: ({ active: source }) => `Выбрана запись ${source.data.current?.entry.source_name ?? ""}`,
          onDragOver: ({ over }) => over ? `Приём пищи: ${meals.find((meal) => meal.type === over.id)?.label ?? ""}` : "Вне приёмов пищи",
          onDragEnd: ({ over }) => over ? "Перенос завершён" : "Перенос отменён",
          onDragCancel: () => "Перенос отменён",
        },
      }}
    >
      <div className={`meals-list ${active ? "is-drag-active" : ""}`}>
        {meals.filter((meal) => active || meal.type !== "other" || meal.entries.length > 0).map((meal) => <MealSection key={meal.type} {...props} meal={meal} active={active} swiped={swiped} setSwiped={setSwiped} />)}
      </div>
      {createPortal(<DragOverlay dropAnimation={reducedMotion ? null : { duration: 180, easing: "ease-out" }} zIndex={90}>
        {active && <div className="meal-entry-drag-preview" aria-hidden="true"><div className="meal-entry__main"><EntrySummary entry={active} format={props.format} formatValue={props.formatValue} /></div></div>}
      </DragOverlay>, document.body)}
    </DndContext>
  );
}
