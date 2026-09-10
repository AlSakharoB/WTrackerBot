import { useMutation } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { useRef, useState } from "react";

import {
  APIError,
  createWeightEntry,
  deleteWeightEntry,
  updateWeightEntry,
  type WeightEntry,
} from "../../api/client";
import { BottomSheet, ConfirmDialog, FormField, useToast } from "../ui";

function mutationKey(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
}

function localDateTime(value: Date | string, timezone: string): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(value));
  const get = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((part) => part.type === type)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")}T${get("hour")}:${get("minute")}`;
}

interface WeightEntrySheetProps {
  open: boolean;
  entry: WeightEntry | null;
  timezone: string;
  initData: string;
  authorized: boolean;
  onClose: () => void;
  onChanged: () => void;
}

export function WeightEntrySheet({
  open,
  entry,
  timezone,
  initData,
  authorized,
  onClose,
  onChanged,
}: WeightEntrySheetProps) {
  const { showToast } = useToast();
  const [weight, setWeight] = useState(entry?.weight_kg ?? "");
  const [measuredAt, setMeasuredAt] = useState(() =>
    localDateTime(entry?.measured_at ?? new Date(), timezone),
  );
  const [note, setNote] = useState(entry?.note ?? "");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const idempotencyKey = useRef(mutationKey());

  const saveMutation = useMutation({
    mutationFn: () => {
      if (!authorized) return Promise.resolve(null);
      if (entry) {
        return updateWeightEntry(initData, entry.id, {
          expected_updated_at: entry.updated_at,
          ...(weight !== entry.weight_kg ? { weight_kg: weight } : {}),
          ...(measuredAt !== localDateTime(entry.measured_at, timezone)
            ? { measured_at: measuredAt }
            : {}),
          ...(note !== (entry.note ?? "") ? { note: note.trim() || null } : {}),
        });
      }
      return createWeightEntry(
        initData,
        { weight_kg: weight, measured_at: measuredAt, note: note.trim() || null },
        idempotencyKey.current,
      );
    },
    onSuccess: () => {
      idempotencyKey.current = mutationKey();
      showToast(entry ? "Измерение обновлено" : "Вес записан");
      onChanged();
    },
  });
  const deleteMutation = useMutation({
    mutationFn: () => {
      if (!entry || !authorized) return Promise.resolve();
      return deleteWeightEntry(initData, entry.id);
    },
    onSuccess: () => {
      showToast("Измерение удалено");
      setConfirmDelete(false);
      onChanged();
    },
  });

  const normalizedWeight = weight.trim().replace(",", ".");
  const weightNumber = Number(normalizedWeight);
  const weightError = /^\d+(?:\.\d{1,2})?$/.test(normalizedWeight)
    && Number.isFinite(weightNumber)
    && weightNumber >= 20
    && weightNumber <= 500
    ? undefined
    : "Введите вес от 20 до 500 кг";
  const measuredAtError = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(measuredAt)
    ? undefined
    : "Укажите дату и время";
  const originalMeasuredAt = entry ? localDateTime(entry.measured_at, timezone) : "";
  const hasChanges = !entry
    || weight !== entry.weight_kg
    || measuredAt !== originalMeasuredAt
    || note !== (entry.note ?? "");
  const error = saveMutation.error ?? deleteMutation.error;

  return (
    <>
      <BottomSheet open={open} title={entry ? "Изменить измерение" : "Записать вес"} onClose={onClose}>
        <form
          className="weight-entry-form"
          onSubmit={(event) => {
            event.preventDefault();
            if (!weightError && !measuredAtError && hasChanges && !saveMutation.isPending) {
              saveMutation.mutate();
            }
          }}
        >
          <div className="entry-form-grid">
            <FormField label="Вес, кг" htmlFor="weight-value" error={weightError}>
              <input
                id="weight-value"
                inputMode="decimal"
                autoFocus
                value={weight}
                onChange={(event) => {
                  setWeight(event.target.value);
                  idempotencyKey.current = mutationKey();
                }}
                placeholder="Например, 72,4"
              />
            </FormField>
            <FormField label="Дата и время" htmlFor="weight-measured-at" error={measuredAtError}>
              <input
                id="weight-measured-at"
                type="datetime-local"
                value={measuredAt}
                onChange={(event) => {
                  setMeasuredAt(event.target.value);
                  idempotencyKey.current = mutationKey();
                }}
              />
            </FormField>
          </div>
          <FormField label="Заметка" htmlFor="weight-note" hint="Необязательно, до 1000 символов">
            <textarea
              id="weight-note"
              rows={3}
              maxLength={1000}
              value={note}
              onChange={(event) => {
                setNote(event.target.value);
                idempotencyKey.current = mutationKey();
              }}
              placeholder="Самочувствие или условия измерения"
            />
          </FormField>
          {error && <p className="form-error">{error.message}</p>}
          {error instanceof APIError && error.status === 409 && (
            <button type="button" className="button-text" onClick={onChanged}>Обновить историю</button>
          )}
          <div className="weight-form-actions">
            {entry && (
              <button
                type="button"
                className="button-text button-text--danger"
                onClick={() => setConfirmDelete(true)}
              >
                <Trash2 aria-hidden="true" size={17} /> Удалить
              </button>
            )}
            <div className="form-actions">
              <button type="button" className="button-secondary" onClick={onClose}>Отмена</button>
              <button
                type="submit"
                className="button-primary"
                disabled={Boolean(weightError || measuredAtError) || !hasChanges || saveMutation.isPending}
              >
                {saveMutation.isPending ? "Сохраняем..." : "Сохранить"}
              </button>
            </div>
          </div>
        </form>
      </BottomSheet>
      <ConfirmDialog
        open={confirmDelete}
        title="Удалить измерение?"
        description="Запись исчезнет из истории и графика веса."
        confirmLabel={deleteMutation.isPending ? "Удаляем..." : "Удалить"}
        destructive
        onClose={() => setConfirmDelete(false)}
        onConfirm={() => {
          if (!deleteMutation.isPending) deleteMutation.mutate();
        }}
      />
    </>
  );
}
