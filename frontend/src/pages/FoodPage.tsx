import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  CookingPot,
  Copy,
  Folder,
  FolderCog,
  FolderInput,
  Link2,
  MoreVertical,
  Plus,
  QrCode,
  RefreshCw,
  Salad,
  Search,
  Share2,
  X,
} from "lucide-react";
import { useDeferredValue, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import {
  createSharingPackage,
  fetchDishes,
  fetchFoodFolders,
  fetchIngredients,
  moveFoodItems,
  revokeSharingPackage,
  type Dish,
  type FoodKind,
  type FoodPageResult,
  type FoodSort,
  type Ingredient,
  type SharingPackage,
} from "../api/client";
import { useMiniAppContext } from "../app/context";
import { FoodEditorSheet } from "../components/food/FoodEditorSheet";
import { FolderManagerSheet } from "../components/food/FolderManagerSheet";
import {
  BottomSheet,
  EmptyState,
  ErrorState,
  SegmentedControl,
  Skeleton,
  useToast,
} from "../components/ui";

const FOOD_OPTIONS = [
  { value: "ingredients", label: "Ингредиенты" },
  { value: "dishes", label: "Блюда" },
] as const;

type FoodItem = Ingredient | Dish;

function mutationKey(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
}

function isDish(item: FoodItem): item is Dish {
  return "components" in item;
}

function display(value: string): string {
  return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 }).format(Number(value));
}

function NutritionLine({ item }: { item: FoodItem }) {
  const nutrition = item.nutrition_per_100g;
  return (
    <span>
      {display(nutrition.energy_kcal)} ккал · Б {display(nutrition.protein_g)} · Ж {display(nutrition.fat_g)} · У {display(nutrition.carbs_g)}
      {isDish(item) ? ` / 100 г · всего ${display(item.total_weight_g)} г` : " / 100 г"}
    </span>
  );
}

export function FoodPage() {
  const { initData } = useMiniAppContext();
  const authorized = Boolean(initData);
  const { showToast } = useToast();
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [kind, setKind] = useState<FoodKind>("ingredients");
  const [query, setQuery] = useState("");
  const deferredQuery = useDeferredValue(query);
  const [sort, setSort] = useState<FoodSort>("name_asc");
  const [folder, setFolder] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [editing, setEditing] = useState<FoodItem | null>(null);
  const [share, setShare] = useState<SharingPackage | null>(null);
  const [foldersOpen, setFoldersOpen] = useState(false);
  const [movingItem, setMovingItem] = useState<FoodItem | null>(null);
  const [movingSelection, setMovingSelection] = useState(false);
  const shareMutationKey = useRef(mutationKey());
  const editorOpen = location.pathname.startsWith("/food/new") || editing !== null;

  const foods = useInfiniteQuery({
    queryKey: ["food", kind, deferredQuery, sort, folder],
    queryFn: async ({ pageParam }): Promise<FoodPageResult<FoodItem>> =>
      kind === "ingredients"
        ? await fetchIngredients(initData, deferredQuery, sort, pageParam, folder || undefined)
        : await fetchDishes(initData, deferredQuery, sort, pageParam, folder || undefined),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    enabled: authorized,
    retry: false,
  });
  const items = foods.data?.pages.flatMap((page) => page.items) ?? [];
  const foldersQuery = useQuery({
    queryKey: ["food-folders"],
    queryFn: () => fetchFoodFolders(initData),
    enabled: authorized,
    retry: false,
  });
  const folders = foldersQuery.data ?? [];

  const sharing = useMutation({
    mutationFn: () =>
      createSharingPackage(initData, kind, [...selected], shareMutationKey.current),
    onSuccess: (created) => setShare(created),
  });
  const revoke = useMutation({
    mutationFn: () => revokeSharingPackage(initData, share!.id),
    onSuccess: () => {
      setShare(null);
      setSelected(new Set());
      showToast("Ссылка отозвана");
    },
  });
  const moveItems = useMutation({
    mutationFn: (folderId: string | null) =>
      moveFoodItems(
        initData,
        kind === "ingredients" ? "ingredient" : "dish",
        movingItem ? [movingItem.id] : [...selected],
        folderId,
      ),
    onSuccess: async () => {
      setMovingItem(null);
      setMovingSelection(false);
      setSelected(new Set());
      await queryClient.invalidateQueries({ queryKey: ["food"] });
      await queryClient.invalidateQueries({ queryKey: ["food-folders"] });
      showToast("Позиции перемещены");
    },
  });

  const changeKind = (value: FoodKind) => {
    setKind(value);
    setSelected(new Set());
    shareMutationKey.current = mutationKey();
    setEditing(null);
  };
  const openCreate = () => {
    setEditing(null);
    navigate(`/food/new?kind=${kind}`);
  };
  const closeEditor = () => {
    setEditing(null);
    navigate("/food", { replace: true });
  };
  const openExisting = (item: FoodItem) => {
    setEditing(item);
    navigate("/food", { replace: true });
  };
  const toggle = (id: string) => {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      shareMutationKey.current = mutationKey();
      return next;
    });
  };
  const copyLink = async () => {
    if (!share) return;
    await navigator.clipboard.writeText(share.deep_link);
    showToast("Ссылка скопирована");
  };

  return (
    <div className="page food-page">
      <div className="food-controls">
        <SegmentedControl label="Тип еды" options={FOOD_OPTIONS} value={kind} onChange={changeKind} />
        <div className="food-search-row">
          <div className="search-field">
            <Search aria-hidden="true" size={19} />
            <label className="sr-only" htmlFor="food-search">Поиск еды</label>
            <input id="food-search" type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder={kind === "ingredients" ? "Найти ингредиент" : "Найти блюдо"} />
          </div>
          <button type="button" className="icon-button" aria-label="Сканировать штрихкод" title="Сканировать штрихкод" disabled><QrCode aria-hidden="true" /></button>
          <button type="button" className="icon-button icon-button--primary" aria-label="Добавить" title="Добавить" onClick={openCreate}><Plus aria-hidden="true" /></button>
        </div>
        <div className="food-filter-row">
          <label><Folder aria-hidden="true" /><span className="sr-only">Папка</span><select value={folder} onChange={(event) => setFolder(event.target.value)}><option value="">Все продукты</option><option value="unfiled">Без папки</option>{folders.map((item) => <option key={item.id} value={item.id}>{item.name} ({kind === "ingredients" ? item.ingredient_count : item.dish_count})</option>)}</select></label>
          <label><span className="sr-only">Сортировка</span><select value={sort} onChange={(event) => setSort(event.target.value as FoodSort)}><option value="name_asc">По названию А–Я</option><option value="name_desc">По названию Я–А</option><option value="newest">Сначала новые</option><option value="oldest">Сначала старые</option></select></label>
          <button type="button" className="icon-button" aria-label="Управлять папками" title="Управлять папками" onClick={() => setFoldersOpen(true)}><FolderCog aria-hidden="true" /></button>
        </div>
      </div>

      {selected.size > 0 && (
        <div className="selection-bar">
          <strong>Выбрано: {selected.size}</strong>
          <button type="button" className="button-secondary button-with-icon" onClick={() => setSelected(new Set())}><X aria-hidden="true" size={17} />Снять</button>
          <button type="button" className="button-secondary button-with-icon" onClick={() => setMovingSelection(true)}><FolderInput aria-hidden="true" size={17} />В папку</button>
          <button type="button" className="button-primary button-with-icon" disabled={sharing.isPending} onClick={() => sharing.mutate()}><Share2 aria-hidden="true" size={17} />Поделиться</button>
        </div>
      )}
      {sharing.error && <p className="form-error">{sharing.error.message}</p>}

      <section className="food-catalog" aria-label="Каталог еды">
        {foods.isPending && authorized ? (
          <Skeleton lines={7} />
        ) : foods.error ? (
          <ErrorState title="Не удалось загрузить каталог" message={foods.error.message} onRetry={() => void foods.refetch()} />
        ) : items.length > 0 ? (
          <div className="food-list">
            {items.map((item) => {
              const checked = selected.has(item.id);
              const Icon = isDish(item) ? CookingPot : Salad;
              return (
                <article className={`food-row ${checked ? "is-selected" : ""}`} key={item.id}>
                  <button type="button" className="food-select" aria-label={`${checked ? "Снять выбор" : "Выбрать"} ${item.name}`} aria-pressed={checked} onClick={() => toggle(item.id)}>{checked ? <Check aria-hidden="true" /> : <Icon aria-hidden="true" />}</button>
                  <button type="button" className="food-row__content" onClick={() => setEditing(item)}>
                    <strong>{item.name}</strong>
                    <NutritionLine item={item} />
                    {isDish(item) && <small>{item.components.length} {item.components.length === 1 ? "компонент" : "компонента"}</small>}
                  </button>
                  <button type="button" className="food-folder-action" aria-label={`Переместить ${item.name} в папку`} title="Переместить в папку" onClick={() => setMovingItem(item)}><MoreVertical aria-hidden="true" /></button>
                </article>
              );
            })}
            {foods.hasNextPage && <button type="button" className="load-more button-secondary button-with-icon" disabled={foods.isFetchingNextPage} onClick={() => void foods.fetchNextPage()}><RefreshCw aria-hidden="true" size={17} />{foods.isFetchingNextPage ? "Загружаем..." : "Показать еще"}</button>}
          </div>
        ) : (
          <EmptyState title={query ? "Ничего не найдено" : kind === "ingredients" ? "Нет ингредиентов" : "Нет блюд"} description={query ? "Измените запрос и попробуйте снова." : "Добавьте первую запись в каталог."} icon={kind === "ingredients" ? Salad : CookingPot} action={<button type="button" className="button-primary button-with-icon" onClick={openCreate}><Plus aria-hidden="true" size={17} />Добавить</button>} />
        )}
      </section>

      {editorOpen && <FoodEditorSheet key={`${editing?.id ?? "new"}-${kind}`} open kind={editing ? (isDish(editing) ? "dishes" : "ingredients") : new URLSearchParams(location.search).get("kind") === "dishes" ? "dishes" : kind} item={editing} folders={folders} initData={initData} authorized={authorized} onClose={closeEditor} onOpenExisting={openExisting} />}

      <FolderManagerSheet open={foldersOpen} initData={initData} folders={folders} onClose={() => setFoldersOpen(false)} />

      <BottomSheet open={movingItem !== null || movingSelection} title="Переместить в папку" onClose={() => { setMovingItem(null); setMovingSelection(false); }}>
        <div className="folder-picker-list">
          <button type="button" className="action-row" disabled={moveItems.isPending} onClick={() => moveItems.mutate(null)}><span><strong>Без папки</strong><small>Убрать текущую привязку</small></span></button>
          {folders.map((item) => <button type="button" className="action-row" key={item.id} disabled={moveItems.isPending} onClick={() => moveItems.mutate(item.id)}><span><strong>{item.name}</strong><small>{item.item_count} поз.</small></span></button>)}
        </div>
        {moveItems.error && <p className="form-error">{moveItems.error.message}</p>}
      </BottomSheet>

      <BottomSheet open={share !== null} title="Ссылка для обмена" onClose={() => setShare(null)}>
        {share && <div className="share-result">
          <div className="share-link"><Link2 aria-hidden="true" /><span>{share.deep_link}</span></div>
          <div className="sheet-actions">
            <button type="button" className="button-secondary button-with-icon" onClick={() => void copyLink()}><Copy aria-hidden="true" size={18} />Копировать</button>
            <a className="button-primary button-with-icon" href={share.telegram_share_url}><Share2 aria-hidden="true" size={18} />Отправить</a>
          </div>
          <button type="button" className="revoke-link" disabled={revoke.isPending} onClick={() => revoke.mutate()}>Отозвать ссылку</button>
        </div>}
      </BottomSheet>
    </div>
  );
}
