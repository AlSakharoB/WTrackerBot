import { useMutation } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { useState } from "react";

import { updateWeightGoal, type WeightGoal } from "../../api/client";
import { BottomSheet, ConfirmDialog, FormField, useToast } from "../ui";

interface WeightGoalSheetProps {
  open: boolean;
  goal: WeightGoal | null;
  initData: string;
  authorized: boolean;
  onClose: () => void;
  onChanged: () => void;
}

export function WeightGoalSheet({
  open,
  goal,
  initData,
  authorized,
  onClose,
  onChanged,
}: WeightGoalSheetProps) {
  const { showToast } = useToast();
  const [target, setTarget] = useState(goal?.target_weight_kg ?? "");
  const [targetDate, setTargetDate] = useState(goal?.target_date ?? "");
  const [confirmDelete, setConfirmDelete] = useState(false);

  const saveMutation = useMutation({
    mutationFn: () => authorized
      ? updateWeightGoal(initData, {
          enabled: true,
          target_weight_kg: target,
          target_date: targetDate || null,
        })
      : Promise.resolve(null),
    onSuccess: () => {
      showToast("Цель веса сохранена");
      onChanged();
    },
  });
  const deleteMutation = useMutation({
    mutationFn: () => authorized
      ? updateWeightGoal(initData, { enabled: false })
      : Promise.resolve(null),
    onSuccess: () => {
      showToast("Цель веса удалена");
      setConfirmDelete(false);
      onChanged();
    },
  });
  const normalizedTarget = target.trim().replace(",", ".");
  const targetNumber = Number(normalizedTarget);
  const targetError = /^\d+(?:\.\d{1,2})?$/.test(normalizedTarget)
    && Number.isFinite(targetNumber)
    && targetNumber >= 20
    && targetNumber <= 500
    ? undefined
    : "Введите вес от 20 до 500 кг";
  const hasChanges = !goal
    || target !== goal.target_weight_kg
    || targetDate !== (goal.target_date ?? "");
  const error = saveMutation.error ?? deleteMutation.error;

  return (
    <>
      <BottomSheet open={open} title={goal ? "Изменить цель" : "Задать цель"} onClose={onClose}>
        <form
          className="weight-entry-form"
          onSubmit={(event) => {
            event.preventDefault();
            if (!targetError && hasChanges && !saveMutation.isPending) saveMutation.mutate();
          }}
        >
          <div className="entry-form-grid">
            <FormField label="Целевой вес, кг" htmlFor="weight-goal" error={targetError}>
              <input
                id="weight-goal"
                inputMode="decimal"
                autoFocus
                value={target}
                onChange={(event) => setTarget(event.target.value)}
                placeholder="Например, 68"
              />
            </FormField>
            <FormField label="Желаемая дата" htmlFor="weight-goal-date" hint="Необязательно">
              <input
                id="weight-goal-date"
                type="date"
                value={targetDate}
                onChange={(event) => setTargetDate(event.target.value)}
              />
            </FormField>
          </div>
          {error && <p className="form-error">{error.message}</p>}
          <div className="weight-form-actions">
            {goal && (
              <button
                type="button"
                className="button-text button-text--danger"
                onClick={() => setConfirmDelete(true)}
              >
                <Trash2 aria-hidden="true" size={17} /> Удалить цель
              </button>
            )}
            <div className="form-actions">
              <button type="button" className="button-secondary" onClick={onClose}>Отмена</button>
              <button
                type="submit"
                className="button-primary"
                disabled={Boolean(targetError) || !hasChanges || saveMutation.isPending}
              >
                {saveMutation.isPending ? "Сохраняем..." : "Сохранить"}
              </button>
            </div>
          </div>
        </form>
      </BottomSheet>
      <ConfirmDialog
        open={confirmDelete}
        title="Удалить цель веса?"
        description="История измерений сохранится, исчезнет только целевой вес."
        confirmLabel={deleteMutation.isPending ? "Удаляем..." : "Удалить цель"}
        destructive
        onClose={() => setConfirmDelete(false)}
        onConfirm={() => {
          if (!deleteMutation.isPending) deleteMutation.mutate();
        }}
      />
    </>
  );
}
