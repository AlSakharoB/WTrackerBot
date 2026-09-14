import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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
type FieldErrors = Record<string, string>;

function mutationKey(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
}

function isDish(item: EditableFood | null): item is Dish {
  return Boolean(item && "components" in item);
}

function ingredientInput(item: EditableFood | null): IngredientInput {
  if (!item || isDish(item)) return { ...EMPTY_INGREDIENT };
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
      const grams = numberValue(component.grams);
      const factor = grams / 100;
      sum.weight += grams;
      sum.energy += numberValue(component.ingredient.nutrition_per_100g.energy_kcal) * factor;
      sum.protein += numberValue(component.ingredient.nutrition_per_100g.protein_g) * factor;
      sum.fat += numberValue(component.ingredient.nutrition_per_100g.fat_g) * factor;
      sum.carbs += numberValue(component.ingredient.nutrition_per_100g.carbs_g) * factor;
      return sum;
    },
    { weight: 0, energy: 0, protein: 0, fat: 0, carbs: 0 },
  );
  const per100 = totals.weight > 0 ? 100 / totals.weight : 0;
  return {
    weight: totals.weight,
    nutrition: {
      energy_kcal: String(totals.energy * per100),
      protein_g: String(totals.protein * per100),
      fat_g: String(totals.fat * per100),
      carbs_g: String(totals.carbs * per100),
    },
  };
}

function display(value: string | number): string {
  return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 }).format(Number(value));
}

function isNonNegativeNumber(value: string): boolean {
  return value.trim() !== "" && Number.isFinite(Number(value.replace(",", "."))) && numberValue(value) >= 0;
}

function fieldError(error: unknown, ...keys: string[]): string | undefined {
  if (!(error instanceof APIError)) return undefined;
  for (const [path, message] of Object.entries(error.fieldErrors ?? {})) {
    if (keys.some((key) => path === key || path.endsWith(`.${key}`))) return message;
  }
  return undefined;
}

function draftSignature(
  kind: FoodKind,
  ingredient: IngredientInput,
  dishName: string,
  dishFolderId: string,
  components: EditableComponent[],
): string {
  return JSON.stringify(
    kind === "ingredients"
      ? ingredient
      : {
          name: dishName,
          folderId: dishFolderId,
          components: components.map(({ ingredient: value, grams }) => [value.id, grams]),
        },
  );
}

interface FoodEditorSheetProps {
  open: boolean;
  kind: FoodKind;
  item: EditableFood | null;
  initData: string;
  authorized: boolean;
  confirmDeletions?: boolean;
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
  confirmDeletions = true,
  folders,
  onClose,
  onOpenExisting,
  onSaved,
}: FoodEditorSheetProps) {
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const initialIngredient = ingredientInput(item);
  const initialDishName = isDish(item) ? item.name : "";
  const initialDishFolderId = isDish(item) ? item.folder_id ?? "" : "";
  const initialComponents = isDish(item) ? item.components : [];
  const initialSignature = draftSignature(kind, initialIngredient, initialDishName, initialDishFolderId, initialComponents);
  const [ingredient, setIngredient] = useState(initialIngredient);
  const [dishName, setDishName] = useState(initialDishName);
  const [dishFolderId, setDishFolderId] = useState(initialDishFolderId);
  const [components, setComponents] = useState<EditableComponent[]>(initialComponents);
  const [pickerQuery, setPickerQuery] = useState("");
  const deferredPickerQuery = useDeferredValue(pickerQuery);
  const [duplicate, setDuplicate] = useState<EditableFood | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [confirmDiscard, setConfirmDiscard] = useState(false);
  const [localErrors, setLocalErrors] = useState<FieldErrors>({});
  const idempotencyKey = useRef(mutationKey());
  const submittingRef = useRef(false);
  const nameRef = useRef<HTMLInputElement>(null);

  const picker = useInfiniteQuery({
    queryKey: ["food-picker", deferredPickerQuery],
    queryFn: ({ pageParam }) => fetchIngredients(initData, deferredPickerQuery, "name_asc", pageParam || undefined),
    initialPageParam: "",
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
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
  const completeSave = async (saved: EditableFood, message: string) => {
    await invalidate();
    showToast(message);
    if (onSaved) onSaved(saved);
    else onClose();
  };
  const handleSaveError = (error: unknown) => {
    submittingRef.current = false;
    if (error instanceof APIError && error.status === 409) {
      const existing = error.details?.existing as EditableFood | undefined;
      if (existing) setDuplicate(existing);
    }
  };
  const saveIngredient = useMutation({
    mutationFn: () => {
      const input: IngredientInput = {
        ...ingredient,
        name: ingredient.name.trim(),
        package_weight_g: ingredient.package_weight_g?.trim() || null,
        photo_url: ingredient.photo_url?.trim() || null,
        source_name: ingredient.source_name?.trim() || null,
        source_url: ingredient.source_url?.trim() || null,
      };
      return item ? updateIngredient(initData, item.id, input) : createIngredient(initData, input, idempotencyKey.current);
    },
    onSuccess: (saved) => completeSave(saved, item ? "Ингредиент обновлен" : "Ингредиент добавлен"),
    onError: handleSaveError,
  });
  const dishInput: DishInput = {
    name: dishName.trim(),
    folder_id: dishFolderId || null,
    components: components.map((component) => ({ ingredient_id: component.ingredient.id, grams: component.grams })),
  };
  const saveDish = useMutation({
    mutationFn: () => item ? updateDish(initData, item.id, dishInput) : createDish(initData, dishInput, idempotencyKey.current),
    onSuccess: (saved) => completeSave(saved, item ? "Блюдо обновлено" : "Блюдо добавлено"),
    onError: handleSaveError,
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
  const pickerItems = (picker.data?.pages.flatMap((page) => page.items) ?? []).filter(
    (candidate) => !components.some((value) => value.ingredient.id === candidate.id),
  );
  const isDirty = draftSignature(kind, ingredient, dishName, dishFolderId, components) !== initialSignature;
  const pending = saveIngredient.isPending || saveDish.isPending;
  const dishReady = Boolean(
    dishName.trim()
    && components.length
    && components.every((component) => isNonNegativeNumber(component.grams) && numberValue(component.grams) > 0),
  );
  const mutationError = saveIngredient.error ?? saveDish.error;
  const generalError = mutationError instanceof APIError && (mutationError.status === 409 || mutationError.fieldErrors)
    ? undefined
    : mutationError instanceof Error ? mutationError.message : undefined;

  const updateIngredientField = <K extends keyof IngredientInput>(key: K, value: IngredientInput[K]) => {
    setIngredient((current) => ({ ...current, [key]: value }));
    setLocalErrors((current) => ({ ...current, [key]: "" }));
    setDuplicate(null);
    idempotencyKey.current = mutationKey();
  };
  const updateDishDraft = () => {
    setDuplicate(null);
    idempotencyKey.current = mutationKey();
  };
  const move = (index: number, direction: -1 | 1) => {
    const target = index + direction;
    if (target < 0 || target >= components.length) return;
    setComponents((current) => {
      const next = [...current];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
    updateDishDraft();
  };
  const requestClose = () => {
    if (pending) return;
    if (isDirty) setConfirmDiscard(true);
    else onClose();
  };
  const focusName = () => {
    setDuplicate(null);
    nameRef.current?.focus();
    nameRef.current?.select();
  };
  const requestDelete = async () => {
    if (confirmDeletions) {
      setConfirmDelete(true);
      return;
    }
    const result = await consequence.refetch();
    if (result.data?.can_delete && !remove.isPending) remove.mutate();
    else setConfirmDelete(true);
  };
  const submitIngredient = () => {
    const errors: FieldErrors = {};
    if (!ingredient.name.trim()) errors.name = "Введите название";
    for (const key of ["energy_kcal_per_100g", "protein_g_per_100g", "fat_g_per_100g", "carbs_g_per_100g"] as const) {
      if (!isNonNegativeNumber(ingredient[key])) errors[key] = "Введите число не меньше нуля";
    }
    if (ingredient.package_weight_g && !isNonNegativeNumber(ingredient.package_weight_g)) errors.package_weight_g = "Введите число не меньше нуля";
    setLocalErrors(errors);
    if (Object.keys(errors).length || submittingRef.current) return;
    submittingRef.current = true;
    saveIngredient.mutate();
  };
  const submitDish = () => {
    const errors: FieldErrors = {};
    if (!dishName.trim()) errors.name = "Введите название";
    if (components.length === 0) errors.components = "Добавьте хотя бы один ингредиент";
    components.forEach((component) => {
      if (!isNonNegativeNumber(component.grams) || numberValue(component.grams) <= 0) errors[`grams.${component.ingredient.id}`] = "Вес должен быть больше нуля";
    });
    setLocalErrors(errors);
    if (Object.keys(errors).length || submittingRef.current) return;
    submittingRef.current = true;
    saveDish.mutate();
  };

  return (
    <>
      <BottomSheet open={open} title={`${item ? "Изменить" : "Добавить"} ${kind === "ingredients" ? "ингредиент" : "блюдо"}`} onClose={requestClose}>
        {kind === "ingredients" ? (
          <form className="food-editor" onSubmit={(event) => { event.preventDefault(); submitIngredient(); }}>
            <FormField label="Название" htmlFor="ingredient-name" error={localErrors.name || fieldError(mutationError, "name")}><input ref={nameRef} id="ingredient-name" value={ingredient.name} onChange={(event) => updateIngredientField("name", event.target.value)} autoFocus maxLength={255} /></FormField>
            <FormField label="Папка" htmlFor="ingredient-folder" error={fieldError(mutationError, "folder_id")}><select id="ingredient-folder" value={ingredient.folder_id ?? ""} onChange={(event) => updateIngredientField("folder_id", event.target.value || null)}><option value="">Без папки</option>{folders.map((folder) => <option key={folder.id} value={folder.id}>{folder.name}</option>)}</select></FormField>
            <fieldset className="nutrition-fields">
              <legend>КБЖУ на 100 г</legend>
              <FormField label="Ккал" htmlFor="ingredient-kcal" error={localErrors.energy_kcal_per_100g || fieldError(mutationError, "energy_kcal_per_100g")}><input id="ingredient-kcal" inputMode="decimal" value={ingredient.energy_kcal_per_100g} onChange={(event) => updateIngredientField("energy_kcal_per_100g", event.target.value)} /></FormField>
              <FormField label="Белки, г" htmlFor="ingredient-protein" error={localErrors.protein_g_per_100g || fieldError(mutationError, "protein_g_per_100g")}><input id="ingredient-protein" inputMode="decimal" value={ingredient.protein_g_per_100g} onChange={(event) => updateIngredientField("protein_g_per_100g", event.target.value)} /></FormField>
              <FormField label="Жиры, г" htmlFor="ingredient-fat" error={localErrors.fat_g_per_100g || fieldError(mutationError, "fat_g_per_100g")}><input id="ingredient-fat" inputMode="decimal" value={ingredient.fat_g_per_100g} onChange={(event) => updateIngredientField("fat_g_per_100g", event.target.value)} /></FormField>
              <FormField label="Углеводы, г" htmlFor="ingredient-carbs" error={localErrors.carbs_g_per_100g || fieldError(mutationError, "carbs_g_per_100g")}><input id="ingredient-carbs" inputMode="decimal" value={ingredient.carbs_g_per_100g} onChange={(event) => updateIngredientField("carbs_g_per_100g", event.target.value)} /></FormField>
            </fieldset>
            <details className="food-editor-details">
              <summary>Упаковка, фото и источник</summary>
              <div className="ingredient-metadata-fields">
                <FormField label="Вес упаковки, г" htmlFor="ingredient-package-weight" error={localErrors.package_weight_g || fieldError(mutationError, "package_weight_g")}><input id="ingredient-package-weight" inputMode="decimal" value={ingredient.package_weight_g ?? ""} onChange={(event) => updateIngredientField("package_weight_g", event.target.value)} /></FormField>
                <FormField label="Фото" htmlFor="ingredient-photo" error={fieldError(mutationError, "photo_url")}><input id="ingredient-photo" type="url" placeholder="https://" value={ingredient.photo_url ?? ""} onChange={(event) => updateIngredientField("photo_url", event.target.value)} /></FormField>
                <FormField label="Источник" htmlFor="ingredient-source" error={fieldError(mutationError, "source_name")}><input id="ingredient-source" value={ingredient.source_name ?? ""} onChange={(event) => updateIngredientField("source_name", event.target.value)} maxLength={100} /></FormField>
                <FormField label="Ссылка на источник" htmlFor="ingredient-source-url" error={fieldError(mutationError, "source_url")}><input id="ingredient-source-url" type="url" placeholder="https://" value={ingredient.source_url ?? ""} onChange={(event) => updateIngredientField("source_url", event.target.value)} /></FormField>
              </div>
            </details>
            {duplicate && <div className="duplicate-notice" role="alert"><div><strong>Такой ингредиент уже существует</strong><span>{duplicate.name}</span></div><div className="duplicate-notice__actions"><button type="button" onClick={() => onOpenExisting(duplicate)}>Открыть</button><button type="button" onClick={focusName}>Изменить название</button></div></div>}
            {generalError && <p className="form-error" role="alert">{generalError}</p>}
            <div className="sheet-actions">{item && <button type="button" className="button-danger button-with-icon" disabled={consequence.isFetching || remove.isPending} onClick={() => void requestDelete()}><Trash2 aria-hidden="true" size={18} />{consequence.isFetching ? "Проверяем..." : "Удалить"}</button>}<button type="submit" className="button-primary" disabled={pending}>{pending ? "Сохраняем..." : "Сохранить"}</button></div>
          </form>
        ) : (
          <form className="food-editor food-editor--dish" onSubmit={(event) => { event.preventDefault(); submitDish(); }}>
            <div className="dish-main-fields">
              <FormField label="Название" htmlFor="dish-name" error={localErrors.name || fieldError(mutationError, "name")}><input ref={nameRef} id="dish-name" value={dishName} onChange={(event) => { setDishName(event.target.value); setLocalErrors((current) => ({ ...current, name: "" })); updateDishDraft(); }} autoFocus maxLength={255} /></FormField>
              <FormField label="Папка" htmlFor="dish-folder" error={fieldError(mutationError, "folder_id")}><select id="dish-folder" value={dishFolderId} onChange={(event) => { setDishFolderId(event.target.value); updateDishDraft(); }}><option value="">Без папки</option>{folders.map((folder) => <option key={folder.id} value={folder.id}>{folder.name}</option>)}</select></FormField>
            </div>
            <div className="dish-workspace">
              <section className="dish-composition" aria-labelledby="dish-components-heading">
                <div className="dish-components__heading"><strong id="dish-components-heading">Состав</strong><span>{components.length}</span></div>
                <div className="dish-components">
                  {components.map((component, index) => (
                    <div className="dish-component" key={component.ingredient.id}>
                      <div><strong>{component.ingredient.name}</strong><small>{display(component.ingredient.nutrition_per_100g.energy_kcal)} ккал / 100 г</small></div>
                      <FormField label={`Вес ${component.ingredient.name}, г`} htmlFor={`dish-grams-${component.ingredient.id}`} error={localErrors[`grams.${component.ingredient.id}`] || fieldError(mutationError, `components.${index}.grams`, "grams")}><input id={`dish-grams-${component.ingredient.id}`} inputMode="decimal" value={component.grams} onChange={(event) => { const grams = event.target.value; setComponents((current) => current.map((value, componentIndex) => componentIndex === index ? { ...value, grams } : value)); setLocalErrors((current) => ({ ...current, [`grams.${component.ingredient.id}`]: "" })); updateDishDraft(); }} /></FormField>
                      <div className="component-actions">
                        <button type="button" disabled={index === 0} onClick={() => move(index, -1)} aria-label={`Переместить ${component.ingredient.name} выше`} title="Выше"><ArrowUp aria-hidden="true" /></button>
                        <button type="button" disabled={index === components.length - 1} onClick={() => move(index, 1)} aria-label={`Переместить ${component.ingredient.name} ниже`} title="Ниже"><ArrowDown aria-hidden="true" /></button>
                        <button type="button" onClick={() => { setComponents((current) => current.filter((_, componentIndex) => componentIndex !== index)); updateDishDraft(); }} aria-label={`Удалить ${component.ingredient.name} из блюда`} title="Удалить"><X aria-hidden="true" /></button>
                      </div>
                    </div>
                  ))}
                  {components.length === 0 && <p className={`inline-empty ${localErrors.components ? "has-error" : ""}`} role={localErrors.components ? "alert" : undefined}>{localErrors.components ?? "Найдите ингредиенты справа и добавьте их в состав."}</p>}
                </div>
                <div className="dish-total" aria-label="Итоги блюда"><div><span>Вес</span><strong>{display(totals.weight)} г</strong></div><div><span>Ккал / 100 г</span><strong>{display(totals.nutrition.energy_kcal)}</strong></div><div><span>Б / 100 г</span><strong>{display(totals.nutrition.protein_g)} г</strong></div><div><span>Ж / 100 г</span><strong>{display(totals.nutrition.fat_g)} г</strong></div><div><span>У / 100 г</span><strong>{display(totals.nutrition.carbs_g)} г</strong></div></div>
              </section>
              <aside className="dish-picker" aria-label="Поиск ингредиентов">
                <div className="search-field"><Search aria-hidden="true" size={18} /><label className="sr-only" htmlFor="dish-ingredient-search">Найти ингредиент</label><input id="dish-ingredient-search" type="search" value={pickerQuery} onChange={(event) => setPickerQuery(event.target.value)} placeholder="Добавить ингредиент" /></div>
                {picker.isPending && <div className="picker-status" role="status">Загружаем ингредиенты...</div>}
                {picker.error && <div className="picker-status is-error" role="alert"><span>{picker.error.message}</span><button type="button" onClick={() => void picker.refetch()}>Повторить</button></div>}
                {!picker.isPending && !picker.error && pickerItems.length === 0 && !picker.hasNextPage && <div className="picker-status">{pickerQuery.trim() ? "Ничего не найдено" : components.length ? "Все ингредиенты уже в составе" : "Ингредиентов пока нет"}</div>}
                {(pickerItems.length > 0 || picker.hasNextPage) && <div className="ingredient-picker-results">{pickerItems.map((candidate) => <button type="button" key={candidate.id} onClick={() => { setComponents((current) => [...current, { ingredient: candidate, grams: "100" }]); setPickerQuery(""); setLocalErrors((current) => ({ ...current, components: "" })); updateDishDraft(); }}><Plus aria-hidden="true" /><span><strong>{candidate.name}</strong><small>{display(candidate.nutrition_per_100g.energy_kcal)} ккал / 100 г</small></span></button>)}{picker.hasNextPage && <button type="button" className="picker-load-more" disabled={picker.isFetchingNextPage} onClick={() => void picker.fetchNextPage()}>{picker.isFetchingNextPage ? "Загружаем..." : "Показать ещё"}</button>}</div>}
              </aside>
            </div>
            {duplicate && <div className="duplicate-notice" role="alert"><div><strong>Такое блюдо уже существует</strong><span>{duplicate.name}</span></div><div className="duplicate-notice__actions"><button type="button" onClick={() => onOpenExisting(duplicate)}>Открыть</button><button type="button" onClick={focusName}>Изменить название</button></div></div>}
            {generalError && <p className="form-error" role="alert">{generalError}</p>}
            <div className="sheet-actions">{item && <button type="button" className="button-danger button-with-icon" disabled={consequence.isFetching || remove.isPending} onClick={() => void requestDelete()}><Trash2 aria-hidden="true" size={18} />{consequence.isFetching ? "Проверяем..." : "Удалить"}</button>}<button type="submit" className="button-primary" disabled={pending || !dishReady}>{pending ? "Сохраняем..." : "Сохранить"}</button></div>
          </form>
        )}
      </BottomSheet>
      <ConfirmDialog open={confirmDiscard} title="Отменить изменения?" description="Несохраненные данные будут потеряны." confirmLabel="Выйти без сохранения" destructive onClose={() => setConfirmDiscard(false)} onConfirm={onClose} />
      <ConfirmDialog open={confirmDelete} title={consequence.data?.can_delete === false ? "Удаление недоступно" : "Удалить безвозвратно?"} description={consequence.data?.message ?? consequence.error?.message ?? "Проверяем связанные данные..."} confirmLabel={consequence.data?.can_delete === false ? "Понятно" : "Удалить"} destructive={consequence.data?.can_delete !== false} onClose={() => setConfirmDelete(false)} onConfirm={() => { if (consequence.data?.can_delete && !remove.isPending) remove.mutate(); else if (consequence.data) setConfirmDelete(false); }} />
    </>
  );
}
