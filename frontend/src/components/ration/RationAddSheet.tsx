import { useMutation, useQuery } from "@tanstack/react-query";
import { CookingPot, Plus, Salad, Search } from "lucide-react";
import { useDeferredValue, useRef, useState } from "react";
import { Link } from "react-router-dom";

import {
  createRationEntry,
  fetchRationSources,
  type MealType,
  type NumberFormat,
  type RationNutrition,
  type RationSource,
  type RationSourceKind,
} from "../../api/client";
import { BottomSheet, FormField, SegmentedControl, Skeleton, useToast } from "../ui";

const SOURCE_OPTIONS = [
  { value: "all", label: "Все" },
  { value: "ingredient", label: "Ингредиенты" },
  { value: "dish", label: "Блюда" },
] as const;

const MEAL_OPTIONS: Array<{ value: MealType; label: string }> = [
  { value: "breakfast", label: "Завтрак" },
  { value: "lunch", label: "Обед" },
  { value: "dinner", label: "Ужин" },
  { value: "snack", label: "Перекус" },
  { value: "other", label: "Другое" },
];

function mutationKey(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
}

function gramsValue(raw: string): number {
  const value = Number(raw.trim().replace(",", "."));
  return Number.isFinite(value) ? value : 0;
}

function scaledNutrition(source: RationSource, grams: string): RationNutrition {
  const factor = gramsValue(grams) / 100;
  const scale = (value: string) => String(Number(value) * factor);
  return {
    energy_kcal: scale(source.nutrition_per_100g.energy_kcal),
    protein_g: scale(source.nutrition_per_100g.protein_g),
    fat_g: scale(source.nutrition_per_100g.fat_g),
    carbs_g: scale(source.nutrition_per_100g.carbs_g),
  };
}

interface RationAddSheetProps {
  open: boolean;
  date: string;
  initialMeal: MealType;
  format: NumberFormat;
  initData: string;
  authorized: boolean;
  formatValue: (value: string | number, format: NumberFormat) => string;
  onClose: () => void;
  onSaved: () => void;
}

export function RationAddSheet({
  open,
  date,
  initialMeal,
  format,
  initData,
  authorized,
  formatValue,
  onClose,
  onSaved,
}: RationAddSheetProps) {
  const { showToast } = useToast();
  const [kind, setKind] = useState<RationSourceKind>("all");
  const [query, setQuery] = useState("");
  const deferredQuery = useDeferredValue(query);
  const [selected, setSelected] = useState<RationSource | null>(null);
  const [meal, setMeal] = useState<MealType>(initialMeal);
  const [grams, setGrams] = useState("100");
  const idempotencyKey = useRef(mutationKey());

  const sourcesQuery = useQuery({
    queryKey: ["ration-sources", kind, deferredQuery],
    queryFn: () => fetchRationSources(initData, deferredQuery, kind),
    enabled: open && authorized,
    retry: false,
  });
  const createMutation = useMutation({
    mutationFn: () => {
      if (!selected) throw new Error("Выберите продукт или блюдо");
      return createRationEntry(
        initData,
        date,
        {
          source_type: selected.type,
          source_id: selected.id,
          grams,
          meal_type: meal,
        },
        idempotencyKey.current,
      );
    },
    onSuccess: () => {
      idempotencyKey.current = mutationKey();
      showToast("Запись добавлена");
      onSaved();
    },
  });
  const gramNumber = gramsValue(grams);
  const gramsError = grams.trim() && gramNumber >= 0.01 && gramNumber <= 1_000_000
    ? undefined
    : "Введите количество от 0,01 до 1 000 000 г";
  const nutrition = selected ? scaledNutrition(selected, grams) : null;
  const sources = authorized ? sourcesQuery.data ?? [] : [];

  const chooseSource = (source: RationSource) => {
    setSelected(source);
    setGrams(source.default_grams);
    idempotencyKey.current = mutationKey();
  };

  return (
    <BottomSheet open={open} title="Добавить в рацион" onClose={onClose}>
      <div className="ration-picker">
        {!selected ? (
          <>
            <SegmentedControl
              label="Тип источника"
              options={SOURCE_OPTIONS}
              value={kind}
              onChange={setKind}
            />
            <div className="search-field">
              <Search aria-hidden="true" size={19} />
              <label className="sr-only" htmlFor="ration-source-search">Поиск</label>
              <input
                id="ration-source-search"
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Найти ингредиент или блюдо"
                autoFocus
              />
            </div>
            {sourcesQuery.isPending && authorized ? (
              <Skeleton lines={4} />
            ) : sourcesQuery.error ? (
              <p className="form-error">{sourcesQuery.error.message}</p>
            ) : sources.length ? (
              <div className="ration-source-list">
                {sources.map((source) => {
                  const Icon = source.type === "dish" ? CookingPot : Salad;
                  return (
                    <button type="button" key={`${source.type}-${source.id}`} onClick={() => chooseSource(source)}>
                      <span><Icon aria-hidden="true" /></span>
                      <div>
                        <strong>{source.name}</strong>
                        <small>
                          {formatValue(source.nutrition_per_100g.energy_kcal, format)} ккал / 100 г
                          {source.usage_count > 0 && ` · использован ${source.usage_count} раз`}
                          {source.last_used_at && ` · ${new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "short" }).format(new Date(source.last_used_at))}`}
                        </small>
                      </div>
                      <Plus aria-hidden="true" />
                    </button>
                  );
                })}
              </div>
            ) : (
              <div className="picker-empty">
                <strong>{query ? "Ничего не найдено" : "Список пока пуст"}</strong>
                <Link to="/food/new?return=ration">Создать продукт или блюдо</Link>
              </div>
            )}
          </>
        ) : (
          <form className="ration-entry-form" onSubmit={(event) => { event.preventDefault(); createMutation.mutate(); }}>
            <button type="button" className="selected-source" onClick={() => setSelected(null)}>
              <span>{selected.type === "dish" ? <CookingPot aria-hidden="true" /> : <Salad aria-hidden="true" />}</span>
              <div><strong>{selected.name}</strong><small>Нажмите, чтобы выбрать другой источник</small></div>
            </button>
            <div className="entry-form-grid">
              <FormField label="Приём пищи" htmlFor="ration-meal">
                <select id="ration-meal" value={meal} onChange={(event) => { setMeal(event.target.value as MealType); idempotencyKey.current = mutationKey(); }}>
                  {MEAL_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                </select>
              </FormField>
              <FormField label="Количество, г" htmlFor="ration-grams" error={gramsError}>
                <input id="ration-grams" inputMode="decimal" value={grams} onChange={(event) => { setGrams(event.target.value); idempotencyKey.current = mutationKey(); }} />
              </FormField>
            </div>
            {nutrition && (
              <div className="nutrition-preview" aria-label="Расчёт КБЖУ">
                <div><span>Ккал</span><strong>{formatValue(nutrition.energy_kcal, format)}</strong></div>
                <div><span>Белки</span><strong>{formatValue(nutrition.protein_g, format)} г</strong></div>
                <div><span>Жиры</span><strong>{formatValue(nutrition.fat_g, format)} г</strong></div>
                <div><span>Углеводы</span><strong>{formatValue(nutrition.carbs_g, format)} г</strong></div>
              </div>
            )}
            {createMutation.error && <p className="form-error">{createMutation.error.message}</p>}
            <button type="submit" className="button-primary" disabled={Boolean(gramsError) || createMutation.isPending}>
              {createMutation.isPending ? "Добавляем..." : "Добавить в рацион"}
            </button>
          </form>
        )}
      </div>
    </BottomSheet>
  );
}
