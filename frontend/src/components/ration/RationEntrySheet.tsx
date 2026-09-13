import { useMutation } from "@tanstack/react-query";
import { CalendarDays, Copy, CookingPot, Pencil, RefreshCw, Salad, Trash2 } from "lucide-react";
import { useRef, useState } from "react";

import {
  APIError,
  copyRationEntry,
  deleteRationEntry,
  updateRationEntry,
  type MealType,
  type NumberFormat,
  type RationEntry,
} from "../../api/client";
import { BottomSheet, ConfirmDialog, FormField, useToast } from "../ui";

const MEALS: Array<{ value: MealType; label: string }> = [
  { value: "breakfast", label: "Завтрак" },
  { value: "lunch", label: "Обед" },
  { value: "dinner", label: "Ужин" },
  { value: "snack", label: "Перекус" },
  { value: "other", label: "Другое" },
];
const MEAL_LABELS = Object.fromEntries(MEALS.map((meal) => [meal.value, meal.label])) as Record<MealType, string>;

type EditorMode = "details" | "edit" | "copy";

function mutationKey(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
}

interface RationEntrySheetProps {
  entry: RationEntry | null;
  currentDate: string;
  format: NumberFormat;
  initData: string;
  authorized: boolean;
  formatValue: (value: string | number, format: NumberFormat) => string;
  onClose: () => void;
  onChanged: (affectedDate?: string) => void;
  onConflictRefresh: (entryId: string) => Promise<void>;
}

export function RationEntrySheet({
  entry,
  currentDate,
  format,
  initData,
  authorized,
  formatValue,
  onClose,
  onChanged,
  onConflictRefresh,
}: RationEntrySheetProps) {
  const { showToast } = useToast();
  const [mode, setMode] = useState<EditorMode>("details");
  const [grams, setGrams] = useState(entry?.grams ?? "");
  const [meal, setMeal] = useState<MealType>(entry?.meal_type ?? "other");
  const [entryDate, setEntryDate] = useState(currentDate);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [refreshingConflict, setRefreshingConflict] = useState(false);
  const copyKey = useRef(mutationKey());

  const updateMutation = useMutation({
    mutationFn: () => {
      if (!entry) throw new Error("Запись не выбрана");
      return updateRationEntry(initData, entry.id, {
        expected_updated_at: entry.updated_at,
        ...(grams !== entry.grams ? { grams } : {}),
        ...(meal !== entry.meal_type ? { meal_type: meal } : {}),
        ...(entryDate !== currentDate ? { entry_date: entryDate } : {}),
      });
    },
    onSuccess: () => {
      showToast("Запись обновлена");
      onChanged(entryDate);
    },
  });
  const copyMutation = useMutation({
    mutationFn: () => {
      if (!entry) throw new Error("Запись не выбрана");
      return copyRationEntry(initData, entry.id, { entry_date: entryDate, meal_type: meal }, copyKey.current);
    },
    onSuccess: () => {
      copyKey.current = mutationKey();
      showToast("Запись скопирована");
      onChanged(entryDate);
    },
  });
  const deleteMutation = useMutation({
    mutationFn: () => {
      if (!entry) throw new Error("Запись не выбрана");
      return deleteRationEntry(initData, entry.id);
    },
    onSuccess: () => {
      showToast("Запись удалена");
      setConfirmDelete(false);
      onChanged();
    },
  });

  if (!entry) return null;
  const SourceIcon = entry.type === "dish" ? CookingPot : Salad;
  const gramsNumber = Number(grams.trim().replace(",", "."));
  const gramsError = Number.isFinite(gramsNumber) && gramsNumber >= 0.01 && gramsNumber <= 1_000_000
    ? undefined
    : "Введите количество от 0,01 до 1 000 000 г";
  const dateError = /^\d{4}-\d{2}-\d{2}$/.test(entryDate) ? undefined : "Выберите дату";
  const hasChanges = grams !== entry.grams || meal !== entry.meal_type || entryDate !== currentDate;
  const pending = updateMutation.isPending || copyMutation.isPending || deleteMutation.isPending;
  const mutationError = updateMutation.error ?? copyMutation.error ?? deleteMutation.error;
  const isConflict = mutationError instanceof APIError && mutationError.status === 409;
  const dateLabel = new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(new Date(`${currentDate}T12:00:00`));
  const refreshConflict = async () => {
    setRefreshingConflict(true);
    try {
      await onConflictRefresh(entry.id);
    } finally {
      setRefreshingConflict(false);
    }
  };

  return (
    <>
      <BottomSheet open title={mode === "edit" ? "Изменить запись" : mode === "copy" ? "Копировать запись" : "Запись рациона"} onClose={onClose}>
        <div className="entry-details">
          <div className="entry-details__heading"><span><SourceIcon aria-hidden="true" /></span><div><h3>{entry.source_name}</h3><p>{formatValue(entry.grams, format)} г · {entry.type === "dish" ? "Блюдо" : "Ингредиент"}</p></div></div>
          {mode === "details" ? (
            <>
              {!entry.source_available && <p className="source-warning">Исходный продукт удалён. Сохранённые значения записи не изменились.</p>}
              <div className="entry-context"><CalendarDays aria-hidden="true" /><span><strong>{MEAL_LABELS[entry.meal_type]}</strong><small>{dateLabel}</small></span></div>
              <div className="entry-nutrition"><div><span>Калории</span><strong>{formatValue(entry.nutrition.energy_kcal, format)} ккал</strong></div><div><span>Белки</span><strong>{formatValue(entry.nutrition.protein_g, format)} г</strong></div><div><span>Жиры</span><strong>{formatValue(entry.nutrition.fat_g, format)} г</strong></div><div><span>Углеводы</span><strong>{formatValue(entry.nutrition.carbs_g, format)} г</strong></div></div>
              <div className="entry-actions">
                <button type="button" onClick={() => setMode("edit")}><Pencil aria-hidden="true" /><span>Изменить</span></button>
                <button type="button" onClick={() => setMode("copy")}><Copy aria-hidden="true" /><span>Копировать</span></button>
                <button type="button" className="is-danger" onClick={() => setConfirmDelete(true)}><Trash2 aria-hidden="true" /><span>Удалить</span></button>
              </div>
            </>
          ) : (
            <form className="ration-entry-form" onSubmit={(event) => { event.preventDefault(); if (mode === "edit") updateMutation.mutate(); else copyMutation.mutate(); }}>
              <div className="entry-form-grid">
                <FormField label="Дата" htmlFor="entry-date" error={dateError}><input id="entry-date" type="date" value={entryDate} onChange={(event) => { setEntryDate(event.target.value); copyKey.current = mutationKey(); }} /></FormField>
                <FormField label="Приём пищи" htmlFor="entry-meal"><select id="entry-meal" value={meal} onChange={(event) => { setMeal(event.target.value as MealType); copyKey.current = mutationKey(); }}>{MEALS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></FormField>
                {mode === "edit" && <FormField label="Количество, г" htmlFor="entry-grams" error={gramsError} hint={!entry.source_available ? "Исходный продукт удалён, изменить граммы нельзя" : undefined}><input id="entry-grams" inputMode="decimal" value={grams} disabled={!entry.source_available} onChange={(event) => setGrams(event.target.value)} /></FormField>}
              </div>
              {isConflict ? (
                <div className="ration-conflict" role="alert">
                  <div><strong>Запись уже изменилась</strong><span>{mutationError.message}</span></div>
                  <button type="button" className="button-secondary button-with-icon" disabled={refreshingConflict} onClick={() => void refreshConflict()}><RefreshCw aria-hidden="true" />{refreshingConflict ? "Обновляем..." : "Загрузить актуальную"}</button>
                </div>
              ) : mutationError ? <p className="form-error" role="alert">{mutationError.message}</p> : null}
              <div className="form-actions"><button type="button" className="button-secondary" onClick={() => setMode("details")}>Назад</button><button type="submit" className="button-primary" disabled={pending || Boolean(dateError) || (mode === "edit" && (!hasChanges || Boolean(gramsError)))}>{pending ? "Сохраняем..." : mode === "copy" ? "Скопировать" : "Сохранить"}</button></div>
            </form>
          )}
        </div>
      </BottomSheet>
      <ConfirmDialog
        open={confirmDelete}
        title="Удалить запись?"
        description={`${entry.source_name} будет удалён из рациона за этот день.`}
        confirmLabel={deleteMutation.isPending ? "Удаляем..." : "Удалить"}
        destructive
        onClose={() => setConfirmDelete(false)}
        onConfirm={() => { if (authorized && !deleteMutation.isPending) deleteMutation.mutate(); }}
      />
    </>
  );
}
