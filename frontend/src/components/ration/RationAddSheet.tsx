import { useMutation, useQuery } from "@tanstack/react-query";
import {
  Apple,
  ChevronLeft,
  CookingPot,
  Minus,
  MoonStar,
  Plus,
  Salad,
  Search,
  Sun,
  Sunrise,
  Utensils,
} from "lucide-react";
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
import { BottomSheet, ErrorState, SegmentedControl, Skeleton, useToast } from "../ui";

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
const MEAL_ICONS = {
  breakfast: Sunrise,
  lunch: Sun,
  dinner: MoonStar,
  snack: Apple,
  other: Utensils,
} satisfies Record<MealType, typeof Sunrise>;

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
  initialSource?: RationSource | null;
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
  initialSource = null,
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
  const [selected, setSelected] = useState<RationSource | null>(initialSource);
  const [meal, setMeal] = useState<MealType>(initialMeal);
  const [grams, setGrams] = useState(initialSource?.default_grams ?? "100");
  const idempotencyKey = useRef(mutationKey());
  const submissionInFlight = useRef(false);

  const sourcesQuery = useQuery({
    queryKey: ["ration-sources", kind, deferredQuery],
    queryFn: () => fetchRationSources(initData, deferredQuery, kind),
    enabled: open && authorized && selected === null,
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
    createMutation.reset();
  };
  const updateGrams = (value: string) => {
    setGrams(value);
    idempotencyKey.current = mutationKey();
    createMutation.reset();
  };
  const stepGrams = (amount: number) => {
    const next = Math.min(1_000_000, Math.max(0.01, gramNumber + amount));
    updateGrams(String(Math.round(next * 100) / 100));
  };
  const changeMeal = (value: MealType) => {
    setMeal(value);
    idempotencyKey.current = mutationKey();
    createMutation.reset();
  };
  const createPath = (sourceKind: "ingredients" | "dishes") => {
    const params = new URLSearchParams({
      kind: sourceKind,
      return: "ration",
      date,
      meal,
    });
    return `/food/new?${params}`;
  };
  const dateLabel = new Intl.DateTimeFormat("ru-RU", {
    day: "numeric",
    month: "long",
  }).format(new Date(`${date}T12:00:00`));
  const mealLabel = MEAL_OPTIONS.find((option) => option.value === meal)?.label ?? "Другое";
  const submitEntry = () => {
    if (submissionInFlight.current || createMutation.isPending) return;
    submissionInFlight.current = true;
    createMutation.mutate(undefined, {
      onSettled: () => { submissionInFlight.current = false; },
    });
  };

  return (
    <BottomSheet open={open} title="Добавить в рацион" onClose={onClose}>
      <div className="ration-picker">
        <div className="ration-sheet-context">{dateLabel} · {mealLabel}</div>
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
              <ErrorState title="Не удалось загрузить продукты" message={sourcesQuery.error.message} onRetry={() => void sourcesQuery.refetch()} />
            ) : sources.length ? (
              <>
                <div className="ration-picker__list-heading"><strong>{query ? "Результаты" : "Недавние"}</strong><span>{sources.length} поз.</span></div>
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
              </>
            ) : (
              <div className="picker-empty">
                <strong>{query ? "Ничего не найдено" : "Список пока пуст"}</strong>
                <span>{query ? "Создайте новую позицию, если её ещё нет в каталоге." : "Добавьте ингредиент или блюдо в каталог."}</span>
                {kind !== "dish" && <Link className="button-primary" to={createPath("ingredients")}>Создать ингредиент</Link>}
                {kind !== "ingredient" && <Link className="button-secondary" to={createPath("dishes")}>Создать блюдо</Link>}
              </div>
            )}
          </>
        ) : (
          <form className="ration-entry-form" onSubmit={(event) => { event.preventDefault(); submitEntry(); }}>
            <button type="button" className="selected-source" onClick={() => setSelected(null)}>
              <span>{selected.type === "dish" ? <CookingPot aria-hidden="true" /> : <Salad aria-hidden="true" />}</span>
              <div><strong>{selected.name}</strong><small>Нажмите, чтобы выбрать другой источник</small></div>
              <ChevronLeft aria-hidden="true" />
            </button>
            <fieldset className="ration-meal-picker">
              <legend>Приём пищи</legend>
              <div>
                {MEAL_OPTIONS.map((option) => {
                  const Icon = MEAL_ICONS[option.value];
                  return <button type="button" className={meal === option.value ? "is-active" : ""} aria-pressed={meal === option.value} key={option.value} onClick={() => changeMeal(option.value)}><Icon aria-hidden="true" /><span>{option.label}</span></button>;
                })}
              </div>
            </fieldset>
            <div className={`ration-portion ${gramsError ? "has-error" : ""}`}>
              <div><label htmlFor="ration-grams">Количество, г</label><span>Укажите вес порции</span></div>
              <div className="ration-stepper">
                <button type="button" aria-label="Уменьшить количество на 10 грамм" onClick={() => stepGrams(-10)}><Minus aria-hidden="true" /></button>
                <div><input id="ration-grams" inputMode="decimal" value={grams} aria-invalid={Boolean(gramsError)} aria-describedby={gramsError ? "ration-grams-error" : undefined} onChange={(event) => updateGrams(event.target.value)} /><small>г</small></div>
                <button type="button" aria-label="Увеличить количество на 10 грамм" onClick={() => stepGrams(10)}><Plus aria-hidden="true" /></button>
              </div>
            </div>
            {gramsError && <p id="ration-grams-error" className="form-error" role="alert">{gramsError}</p>}
            {nutrition && (
              <div className="nutrition-preview" aria-label="Расчёт КБЖУ">
                <div><span>Ккал</span><strong>{formatValue(nutrition.energy_kcal, format)}</strong></div>
                <div><span>Белки</span><strong>{formatValue(nutrition.protein_g, format)} г</strong></div>
                <div><span>Жиры</span><strong>{formatValue(nutrition.fat_g, format)} г</strong></div>
                <div><span>Углеводы</span><strong>{formatValue(nutrition.carbs_g, format)} г</strong></div>
              </div>
            )}
            {createMutation.error && <p className="form-error" role="alert">{createMutation.error.message}</p>}
            <div className="form-actions"><button type="button" className="button-secondary" onClick={() => setSelected(null)}>Назад</button><button type="submit" className="button-primary" disabled={Boolean(gramsError) || createMutation.isPending}>{createMutation.isPending ? "Добавляем..." : `Добавить в ${mealLabel.toLowerCase()}`}</button></div>
          </form>
        )}
      </div>
    </BottomSheet>
  );
}
