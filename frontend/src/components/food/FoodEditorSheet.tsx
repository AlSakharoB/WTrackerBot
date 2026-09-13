import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Plus, Search, Trash2, X } from "lucide-react";
import { useDeferredValue, useRef, useState } from "react";

import {
  APIError,
  createDish,
  createIngredient,
  deleteFood,
  fetchDeleteConsequence,
  fetchIngredients,
  updateDish,
  updateIngredient,
  type Dish,
  type DishInput,
  type FoodKind,
  type FoodFolder,
  type FoodNutrition,
  type Ingredient,
  type IngredientInput,
} from "../../api/client";
import { BottomSheet, ConfirmDialog, FormField, useToast } from "../ui";

const EMPTY_INGREDIENT: IngredientInput = {
  name: "",
  energy_kcal_per_100g: "",
  protein_g_per_100g: "",
  fat_g_per_100g: "",
  carbs_g_per_100g: "",
  package_weight_g: "",
  photo_url: "",
  source_name: "",
  source_url: "",
  folder_id: null,
};

type EditableFood = Ingredient | Dish;
type EditableComponent = { ingredient: Ingredient; grams: string };

function mutationKey(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
}

function isDish(item: EditableFood | null): item is Dish {
  return Boolean(item && "components" in item);
}

function ingredientInput(item: EditableFood | null): IngredientInput {
  if (!item || isDish(item)) return EMPTY_INGREDIENT;
  return {
    name: item.name,
    energy_kcal_per_100g: item.nutrition_per_100g.energy_kcal,
    protein_g_per_100g: item.nutrition_per_100g.protein_g,
    fat_g_per_100g: item.nutrition_per_100g.fat_g,
    carbs_g_per_100g: item.nutrition_per_100g.carbs_g,
    package_weight_g: item.package_weight_g ?? "",
    photo_url: item.photo_url ?? "",
    source_name: item.source_name ?? "",
    source_url: item.source_url ?? "",
    folder_id: item.folder_id,
  };
}

function numberValue(value: string): number {
  const parsed = Number(value.replace(",", "."));
  return Number.isFinite(parsed) ? parsed : 0;
}

function dishTotals(components: EditableComponent[]): { weight: number; nutrition: FoodNutrition } {
  const totals = components.reduce(
    (sum, component) => {
      const factor = numberValue(component.grams) / 100;
      sum.weight += numberValue(component.grams);
      sum.energy += numberValue(component.ingredient.nutrition_per_100g.energy_kcal) * factor;
      sum.protein += numberValue(component.ingredient.nutrition_per_100g.protein_g) * factor;
      sum.fat += numberValue(component.ingredient.nutrition_per_100g.fat_g) * factor;
      sum.carbs += numberValue(component.ingredient.nutrition_per_100g.carbs_g) * factor;
      return sum;
    },
    { weight: 0, energy: 0, protein: 0, fat: 0, carbs: 0 },
  );
  return {
    weight: totals.weight,
    nutrition: {
      energy_kcal: String(totals.energy),
      protein_g: String(totals.protein),
      fat_g: String(totals.fat),
      carbs_g: String(totals.carbs),
    },
  };
}

function display(value: string | number): string {
  return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 }).format(Number(value));
}

interface FoodEditorSheetProps {
  open: boolean;
  kind: FoodKind;
  item: EditableFood | null;
  initData: string;
  authorized: boolean;
  folders: FoodFolder[];
  onClose: () => void;
  onOpenExisting: (item: EditableFood) => void;
  onSaved?: (item: EditableFood) => void;
}

export function FoodEditorSheet({
  open,
  kind,
  item,
  initData,
  authorized,
  folders,
  onClose,
  onOpenExisting,
  onSaved,
}: FoodEditorSheetProps) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const [ingredient, setIngredient] = useState(() => ingredientInput(item));
  const [dishName, setDishName] = useState(isDish(item) ? item.name : "");
  const [dishFolderId, setDishFolderId] = useState(isDish(item) ? item.folder_id ?? "" : "");
  const [components, setComponents] = useState<EditableComponent[]>(
    isDish(item) ? item.components : [],
  );
  const [pickerQuery, setPickerQuery] = useState("");
  const deferredPickerQuery = useDeferredValue(pickerQuery);
  const [duplicate, setDuplicate] = useState<EditableFood | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const idempotencyKey = useRef(mutationKey());

  const picker = useQuery({
    queryKey: ["food-picker", deferredPickerQuery],
    queryFn: () => fetchIngredients(initData, deferredPickerQuery, "name_asc"),
    enabled: open && kind === "dishes" && authorized,
    retry: false,
  });
  const consequence = useQuery({
    queryKey: ["food-delete-consequence", kind, item?.id],
    queryFn: () => fetchDeleteConsequence(initData, kind, item!.id),
    enabled: confirmDelete && Boolean(item) && authorized,
    retry: false,
  });

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ["food"] });
    await queryClient.invalidateQueries({ queryKey: ["ration-sources"] });
  };
  const saveIngredient = useMutation({
    mutationFn: () => {
      const input: IngredientInput = {
        ...ingredient,
        package_weight_g: ingredient.package_weight_g?.trim() || null,
        photo_url: ingredient.photo_url?.trim() || null,
        source_name: ingredient.source_name?.trim() || null,
        source_url: ingredient.source_url?.trim() || null,
      };
      return (
      item
        ? updateIngredient(initData, item.id, input)
        : createIngredient(initData, input, idempotencyKey.current)
      );
    },
    onSuccess: async (saved) => {
      await invalidate();
      showToast(item ? "Ингредиент обновлен" : "Ингредиент добавлен");
      if (onSaved) onSaved(saved);
      else onClose();
    },
    onError: (error) => {
      if (error instanceof APIError && error.status === 409) {
        const existing = error.details?.existing as EditableFood | undefined;
        if (existing) setDuplicate(existing);
      }
    },
  });
  const dishInput: DishInput = {
    name: dishName,
    folder_id: dishFolderId || null,
    components: components.map((component) => ({
      ingredient_id: component.ingredient.id,
      grams: component.grams,
    })),
  };
  const saveDish = useMutation({
    mutationFn: () =>
      item
        ? updateDish(initData, item.id, dishInput)
        : createDish(initData, dishInput, idempotencyKey.current),
    onSuccess: async (saved) => {
      await invalidate();
      showToast(item ? "Блюдо обновлено" : "Блюдо добавлено");
      if (onSaved) onSaved(saved);
      else onClose();
    },
    onError: (error) => {
      if (error instanceof APIError && error.status === 409) {
        const existing = error.details?.existing as EditableFood | undefined;
        if (existing) setDuplicate(existing);
      }
    },
  });
  const remove = useMutation({
    mutationFn: () => deleteFood(initData, kind, item!.id),
    onSuccess: async () => {
      await invalidate();
      showToast(kind === "ingredients" ? "Ингредиент удален" : "Блюдо удалено");
      onClose();
    },
  });
  const totals = dishTotals(components);
  const pickerItems = (picker.data?.items ?? []).filter(
    (candidate) => !components.some((item) => item.ingredient.id === candidate.id),
  );

  const move = (index: number, direction: -1 | 1) => {
    const target = index + direction;
    if (target < 0 || target >= components.length) return;
    setComponents((current) => {
      const next = [...current];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  };
  const pending = saveIngredient.isPending || saveDish.isPending;
  const mutationError = saveIngredient.error ?? saveDish.error;

  return (
    <>
      <BottomSheet
        open={open}
        title={`${item ? "Изменить" : "Добавить"} ${kind === "ingredients" ? "ингредиент" : "блюдо"}`}
        onClose={onClose}
      >
        {kind === "ingredients" ? (
          <form className="food-editor" onSubmit={(event) => { event.preventDefault(); saveIngredient.mutate(); }}>
            <FormField label="Название" htmlFor="ingredient-name">
              <input id="ingredient-name" value={ingredient.name} onChange={(event) => setIngredient({ ...ingredient, name: event.target.value })} autoFocus />
            </FormField>
            <FormField label="Папка" htmlFor="ingredient-folder">
              <select id="ingredient-folder" value={ingredient.folder_id ?? ""} onChange={(event) => setIngredient({ ...ingredient, folder_id: event.target.value || null })}><option value="">Без папки</option>{folders.map((folder) => <option key={folder.id} value={folder.id}>{folder.name}</option>)}</select>
            </FormField>
            <fieldset className="nutrition-fields">
              <legend>КБЖУ на 100 г</legend>
              <FormField label="Ккал" htmlFor="ingredient-kcal"><input id="ingredient-kcal" inputMode="decimal" value={ingredient.energy_kcal_per_100g} onChange={(event) => setIngredient({ ...ingredient, energy_kcal_per_100g: event.target.value })} /></FormField>
              <FormField label="Белки, г" htmlFor="ingredient-protein"><input id="ingredient-protein" inputMode="decimal" value={ingredient.protein_g_per_100g} onChange={(event) => setIngredient({ ...ingredient, protein_g_per_100g: event.target.value })} /></FormField>
              <FormField label="Жиры, г" htmlFor="ingredient-fat"><input id="ingredient-fat" inputMode="decimal" value={ingredient.fat_g_per_100g} onChange={(event) => setIngredient({ ...ingredient, fat_g_per_100g: event.target.value })} /></FormField>
              <FormField label="Углеводы, г" htmlFor="ingredient-carbs"><input id="ingredient-carbs" inputMode="decimal" value={ingredient.carbs_g_per_100g} onChange={(event) => setIngredient({ ...ingredient, carbs_g_per_100g: event.target.value })} /></FormField>
            </fieldset>
            <div className="ingredient-metadata-fields">
              <FormField label="Вес упаковки, г" htmlFor="ingredient-package-weight"><input id="ingredient-package-weight" inputMode="decimal" value={ingredient.package_weight_g ?? ""} onChange={(event) => setIngredient({ ...ingredient, package_weight_g: event.target.value })} /></FormField>
              <FormField label="Фото" htmlFor="ingredient-photo"><input id="ingredient-photo" type="url" placeholder="https://" value={ingredient.photo_url ?? ""} onChange={(event) => setIngredient({ ...ingredient, photo_url: event.target.value })} /></FormField>
              <FormField label="Источник" htmlFor="ingredient-source"><input id="ingredient-source" value={ingredient.source_name ?? ""} onChange={(event) => setIngredient({ ...ingredient, source_name: event.target.value })} /></FormField>
              <FormField label="Ссылка на источник" htmlFor="ingredient-source-url"><input id="ingredient-source-url" type="url" placeholder="https://" value={ingredient.source_url ?? ""} onChange={(event) => setIngredient({ ...ingredient, source_url: event.target.value })} /></FormField>
            </div>
            {duplicate && (
              <div className="duplicate-notice" role="alert">
                <div><strong>Уже есть похожий продукт</strong><span>{duplicate.name}</span></div>
                <button type="button" onClick={() => onOpenExisting(duplicate)}>Открыть</button>
              </div>
            )}
            {mutationError && <p className="form-error">{mutationError.message}</p>}
            <div className="sheet-actions">
              {item && <button type="button" className="button-danger button-with-icon" onClick={() => setConfirmDelete(true)}><Trash2 aria-hidden="true" size={18} />Удалить</button>}
              <button type="submit" className="button-primary" disabled={pending}>{pending ? "Сохраняем..." : "Сохранить"}</button>
            </div>
          </form>
        ) : (
          <form className="food-editor" onSubmit={(event) => { event.preventDefault(); saveDish.mutate(); }}>
            <FormField label="Название" htmlFor="dish-name"><input id="dish-name" value={dishName} onChange={(event) => setDishName(event.target.value)} autoFocus /></FormField>
            <FormField label="Папка" htmlFor="dish-folder"><select id="dish-folder" value={dishFolderId} onChange={(event) => setDishFolderId(event.target.value)}><option value="">Без папки</option>{folders.map((folder) => <option key={folder.id} value={folder.id}>{folder.name}</option>)}</select></FormField>
            <div className="dish-components">
              <div className="dish-components__heading"><strong>Состав</strong><span>{components.length}</span></div>
              {components.map((component, index) => (
                <div className="dish-component" key={component.ingredient.id}>
                  <div><strong>{component.ingredient.name}</strong><small>{display(component.ingredient.nutrition_per_100g.energy_kcal)} ккал / 100 г</small></div>
                  <label><span className="sr-only">Граммы {component.ingredient.name}</span><input inputMode="decimal" value={component.grams} onChange={(event) => setComponents((current) => current.map((value, componentIndex) => componentIndex === index ? { ...value, grams: event.target.value } : value))} /><small>г</small></label>
                  <div className="component-actions">
                    <button type="button" disabled={index === 0} onClick={() => move(index, -1)} aria-label="Переместить выше"><ArrowUp aria-hidden="true" /></button>
                    <button type="button" disabled={index === components.length - 1} onClick={() => move(index, 1)} aria-label="Переместить ниже"><ArrowDown aria-hidden="true" /></button>
                    <button type="button" onClick={() => setComponents((current) => current.filter((_, componentIndex) => componentIndex !== index))} aria-label="Удалить из блюда"><X aria-hidden="true" /></button>
                  </div>
                </div>
              ))}
            </div>
            <div className="search-field"><Search aria-hidden="true" size={18} /><label className="sr-only" htmlFor="dish-ingredient-search">Найти ингредиент</label><input id="dish-ingredient-search" type="search" value={pickerQuery} onChange={(event) => setPickerQuery(event.target.value)} placeholder="Добавить ингредиент" /></div>
            {pickerItems.length > 0 && (
              <div className="ingredient-picker-results">
                {pickerItems.slice(0, 8).map((candidate) => <button type="button" key={candidate.id} onClick={() => { setComponents((current) => [...current, { ingredient: candidate, grams: "100" }]); setPickerQuery(""); }}><Plus aria-hidden="true" /><span><strong>{candidate.name}</strong><small>{display(candidate.nutrition_per_100g.energy_kcal)} ккал / 100 г</small></span></button>)}
              </div>
            )}
            <div className="dish-total" aria-label="Итоги блюда">
              <div><span>Вес</span><strong>{display(totals.weight)} г</strong></div>
              <div><span>Ккал</span><strong>{display(totals.nutrition.energy_kcal)}</strong></div>
              <div><span>Б</span><strong>{display(totals.nutrition.protein_g)} г</strong></div>
              <div><span>Ж</span><strong>{display(totals.nutrition.fat_g)} г</strong></div>
              <div><span>У</span><strong>{display(totals.nutrition.carbs_g)} г</strong></div>
            </div>
            {duplicate && <div className="duplicate-notice" role="alert"><div><strong>Уже есть похожее блюдо</strong><span>{duplicate.name}</span></div><button type="button" onClick={() => onOpenExisting(duplicate)}>Открыть</button></div>}
            {mutationError && <p className="form-error">{mutationError.message}</p>}
            <div className="sheet-actions">
              {item && <button type="button" className="button-danger button-with-icon" onClick={() => setConfirmDelete(true)}><Trash2 aria-hidden="true" size={18} />Удалить</button>}
              <button type="submit" className="button-primary" disabled={pending || !dishName.trim() || components.length === 0}>{pending ? "Сохраняем..." : "Сохранить"}</button>
            </div>
          </form>
        )}
      </BottomSheet>
      <ConfirmDialog
        open={confirmDelete}
        title={consequence.data?.can_delete === false ? "Удаление недоступно" : "Удалить безвозвратно?"}
        description={consequence.data?.message ?? consequence.error?.message ?? "Проверяем связанные данные..."}
        confirmLabel={consequence.data?.can_delete === false ? "Понятно" : "Удалить"}
        destructive={consequence.data?.can_delete !== false}
        onClose={() => setConfirmDelete(false)}
        onConfirm={() => { if (consequence.data?.can_delete && !remove.isPending) remove.mutate(); else if (consequence.data) setConfirmDelete(false); }}
      />
    </>
  );
}
