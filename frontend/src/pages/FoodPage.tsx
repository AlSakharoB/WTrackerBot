import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  CookingPot,
  Copy,
  FolderCog,
  FolderInput,
  Link2,
  Plus,
  QrCode,
  RefreshCw,
  Salad,
  Search,
  Share2,
  SlidersHorizontal,
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
  type MealType,
  type RationSource,
  type SharingPackage,
} from "../api/client";
import { useMiniAppContext } from "../app/context";
import { FoodEditorSheet } from "../components/food/FoodEditorSheet";
import { BarcodeScannerSheet } from "../components/food/BarcodeScannerSheet";
import { FolderManagerSheet } from "../components/food/FolderManagerSheet";
import {
  BottomSheet,
  ErrorState,
  SegmentedControl,
  useToast,
} from "../components/ui";

const FOOD_OPTIONS = [
  { value: "ingredients", label: "Ингредиенты" },
  { value: "dishes", label: "Блюда" },
] as const;

type FoodItem = Ingredient | Dish;
const MEAL_TYPES = new Set<MealType>(["breakfast", "lunch", "dinner", "snack", "other"]);

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

function FoodListSkeleton() {
  return (
    <div className="food-list food-list-skeleton" aria-busy="true" aria-label="Загрузка каталога">
      <span className="sr-only">Загрузка каталога</span>
      {Array.from({ length: 4 }, (_, index) => <i key={index} />)}
    </div>
  );
}

export function FoodPage() {
  const { initData, profile } = useMiniAppContext();
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
  const [selectionMode, setSelectionMode] = useState(false);
  const [editing, setEditing] = useState<FoodItem | null>(null);
  const [share, setShare] = useState<SharingPackage | null>(null);
  const [foldersOpen, setFoldersOpen] = useState(false);
  const [barcodeScannerOpen, setBarcodeScannerOpen] = useState(false);
  const [movingItem, setMovingItem] = useState<FoodItem | null>(null);
  const [movingSelection, setMovingSelection] = useState(false);
  const [copyError, setCopyError] = useState<string | null>(null);
  const shareMutationKey = useRef(mutationKey());
  const editorOpen = location.pathname.startsWith("/food/new") || editing !== null;
  const editorParams = new URLSearchParams(location.search);
  const returnsToRation = editorParams.get("return") === "ration";
  const returnDate = /^\d{4}-\d{2}-\d{2}$/.test(editorParams.get("date") ?? "")
    ? editorParams.get("date")!
    : new Date().toISOString().slice(0, 10);
  const requestedReturnMeal = editorParams.get("meal") as MealType | null;
  const returnMeal = requestedReturnMeal && MEAL_TYPES.has(requestedReturnMeal)
    ? requestedReturnMeal
    : "other";
  const rationReturnTarget = `/ration/add?date=${returnDate}&meal=${returnMeal}`;

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
    onSuccess: (created) => {
      setShare(created);
      setCopyError(null);
    },
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
      setSelectionMode(false);
      await queryClient.invalidateQueries({ queryKey: ["food"] });
      await queryClient.invalidateQueries({ queryKey: ["food-folders"] });
      showToast("Позиции перемещены");
    },
  });

  const changeKind = (value: FoodKind) => {
    setKind(value);
    setSelected(new Set());
    setSelectionMode(false);
    shareMutationKey.current = mutationKey();
    setEditing(null);
  };
  const openCreate = () => {
    setEditing(null);
    navigate(`/food/new?kind=${kind}`);
  };
  const closeEditor = () => {
    setEditing(null);
    navigate(returnsToRation ? rationReturnTarget : "/food", { replace: true });
  };
  const finishEditor = (saved: FoodItem) => {
    setEditing(null);
    if (!returnsToRation) {
      navigate("/food", { replace: true });
      return;
    }
    const createdRationSource: RationSource = {
      id: saved.id,
      type: isDish(saved) ? "dish" : "ingredient",
      name: saved.name,
      default_grams: isDish(saved) ? saved.total_weight_g : "100",
      nutrition_per_100g: saved.nutrition_per_100g,
      usage_count: 0,
      last_used_at: null,
    };
    navigate(rationReturnTarget, {
      replace: true,
      state: { createdRationSource },
    });
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
    try {
      await navigator.clipboard.writeText(share.deep_link);
      setCopyError(null);
      showToast("Ссылка скопирована");
    } catch {
      setCopyError("Не удалось скопировать автоматически. Выделите ссылку в поле ниже.");
    }
  };
  const clearSelection = () => {
    setSelected(new Set());
    setSelectionMode(false);
    shareMutationKey.current = mutationKey();
  };
  const selectFolder = (value: string) => {
    setFolder(value);
    clearSelection();
  };
  const selectedFolder = folders.find((item) => item.id === folder);
  const folderName = (item: FoodItem) => folders.find((candidate) => candidate.id === item.folder_id)?.name ?? "Без папки";
  const visibleCount = items.length;
  const catalogCaption = query
    ? `Результаты по запросу «${query}»`
    : selectedFolder
      ? selectedFolder.name
      : folder === "unfiled"
        ? "Без папки"
        : kind === "ingredients"
          ? "Все ингредиенты"
          : "Все блюда";

  return (
    <div className="page food-page">
      <header className="food-page-heading">
        <div><span>Каталог</span><h1>Еда</h1><p>{kind === "ingredients" ? "Ингредиенты" : "Блюда"} для рациона</p></div>
        <div className="food-page-heading__actions">
          <button type="button" className="icon-button" aria-label="Сканировать штрихкод" title="Сканировать штрихкод" onClick={() => setBarcodeScannerOpen(true)}><QrCode aria-hidden="true" /></button>
          <button type="button" className="button-primary button-with-icon" onClick={openCreate}><Plus aria-hidden="true" />Добавить</button>
        </div>
      </header>
      <div className="food-controls">
        <div className="food-search-sort">
          <div className="search-field">
            <Search aria-hidden="true" size={19} />
            <label className="sr-only" htmlFor="food-search">Поиск еды</label>
            <input id="food-search" type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder={kind === "ingredients" ? "Найти ингредиент" : "Найти блюдо"} />
          </div>
          <label className="food-sort-control"><SlidersHorizontal aria-hidden="true" /><span className="sr-only">Сортировка</span><select aria-label="Сортировка" value={sort} onChange={(event) => setSort(event.target.value as FoodSort)}><option value="name_asc">А–Я</option><option value="name_desc">Я–А</option><option value="newest">Сначала новые</option><option value="oldest">Сначала старые</option></select></label>
        </div>
        <SegmentedControl label="Тип еды" options={FOOD_OPTIONS} value={kind} onChange={changeKind} />
        <nav className="food-folder-strip" aria-label="Папки еды">
          <button type="button" className={folder === "" ? "is-active" : ""} aria-pressed={folder === ""} onClick={() => selectFolder("")}>Все</button>
          {folders.map((item) => <button type="button" className={folder === item.id ? "is-active" : ""} aria-pressed={folder === item.id} key={item.id} onClick={() => selectFolder(item.id)}>{item.name}<small>{kind === "ingredients" ? item.ingredient_count : item.dish_count}</small></button>)}
          <button type="button" className={folder === "unfiled" ? "is-active" : ""} aria-pressed={folder === "unfiled"} onClick={() => selectFolder("unfiled")}>Без папки</button>
          <button type="button" className="food-folder-manager" aria-label="Управлять папками" title="Управлять папками" onClick={() => setFoldersOpen(true)}><FolderCog aria-hidden="true" /></button>
        </nav>
      </div>

      {selectionMode && (
        <div className="selection-bar">
          <strong>{selected.size ? `Выбрано: ${selected.size}` : "Выберите позиции"}</strong>
          <button type="button" className="button-text button-with-icon" onClick={clearSelection}><X aria-hidden="true" size={17} />Снять выбор</button>
          <button type="button" className="button-secondary button-with-icon" disabled={selected.size === 0} onClick={() => setMovingSelection(true)}><FolderInput aria-hidden="true" size={17} />В папку</button>
          <button type="button" className="button-primary button-with-icon" disabled={selected.size === 0 || sharing.isPending} onClick={() => sharing.mutate()}><Share2 aria-hidden="true" size={17} />Поделиться</button>
        </div>
      )}
      {sharing.error && <p className="form-error" role="alert">{sharing.error.message}</p>}

      <section className="food-catalog" aria-label="Каталог еды">
        <div className="food-catalog__heading"><div><h2>{catalogCaption}</h2><p>{visibleCount} загружено</p></div>{!selectionMode && items.length > 0 && <button type="button" className="button-secondary" onClick={() => setSelectionMode(true)}>Выбрать</button>}</div>
        {foods.isPending && authorized ? (
          <FoodListSkeleton />
        ) : foods.error ? (
          <ErrorState title="Не удалось загрузить каталог" message={foods.error.message} onRetry={() => void foods.refetch()} />
        ) : items.length > 0 ? (
          <div className="food-list">
            {items.map((item) => {
              const checked = selected.has(item.id);
              const Icon = isDish(item) ? CookingPot : Salad;
              return (
                <article className={`food-row ${checked ? "is-selected" : ""} ${selectionMode ? "is-selection-mode" : ""}`} key={item.id}>
                  {selectionMode && <button type="button" className="food-select" aria-label={`${checked ? "Снять выбор" : "Выбрать"} ${item.name}`} aria-pressed={checked} onClick={() => toggle(item.id)}>{checked ? <Check aria-hidden="true" /> : <span aria-hidden="true" />}</button>}
                  <button type="button" className="food-row__content" onClick={() => selectionMode ? toggle(item.id) : setEditing(item)}>
                    <span className="food-row__type"><Icon aria-hidden="true" /></span>
                    <span className="food-row__copy"><strong>{item.name}</strong><NutritionLine item={item} /><small>{folderName(item)}{isDish(item) && ` · ${item.components.length} комп.`}</small></span>
                  </button>
                  <button type="button" className="food-folder-action" aria-label={`Переместить ${item.name} в папку`} title="Переместить в папку" onClick={() => setMovingItem(item)}><FolderInput aria-hidden="true" /></button>
                </article>
              );
            })}
            {foods.hasNextPage && <button type="button" className="load-more button-secondary button-with-icon" disabled={foods.isFetchingNextPage} onClick={() => void foods.fetchNextPage()}><RefreshCw aria-hidden="true" size={17} />{foods.isFetchingNextPage ? "Загружаем..." : "Показать еще"}</button>}
          </div>
        ) : (
          <div className="food-empty">
            {kind === "ingredients" ? <Salad aria-hidden="true" /> : <CookingPot aria-hidden="true" />}
            <strong>{query ? "Ничего не найдено" : folder ? `В папке «${selectedFolder?.name ?? "Без папки"}» пока пусто` : kind === "ingredients" ? "Нет ингредиентов" : "Нет блюд"}</strong>
            <span>{query ? `По запросу «${query}» нет результатов.` : folder ? "Добавьте новую позицию или переместите сюда существующую." : "Добавьте первую позицию в каталог."}</span>
            <div>{query && <button type="button" className="button-secondary" onClick={() => setQuery("")}>Очистить поиск</button>}{folder && <button type="button" className="button-secondary" onClick={() => { selectFolder(""); setSelectionMode(true); }}>Переместить существующие</button>}<button type="button" className="button-primary button-with-icon" onClick={openCreate}><Plus aria-hidden="true" size={17} />{query ? `Создать ${kind === "ingredients" ? "ингредиент" : "блюдо"}` : "Добавить"}</button></div>
          </div>
        )}
      </section>

      {editorOpen && <FoodEditorSheet key={`${editing?.id ?? "new"}-${kind}`} open kind={editing ? (isDish(editing) ? "dishes" : "ingredients") : editorParams.get("kind") === "dishes" ? "dishes" : kind} item={editing} folders={folders} initData={initData} authorized={authorized} confirmDeletions={profile.confirm_deletions} onClose={closeEditor} onOpenExisting={openExisting} onSaved={finishEditor} />}

      <BarcodeScannerSheet open={barcodeScannerOpen} initData={initData} folders={folders} onClose={() => setBarcodeScannerOpen(false)} onOpenExisting={openExisting} />

      <FolderManagerSheet open={foldersOpen} initData={initData} folders={folders} confirmDeletions={profile.confirm_deletions} onClose={() => setFoldersOpen(false)} />

      <BottomSheet open={movingItem !== null || movingSelection} title="Переместить в папку" onClose={() => { setMovingItem(null); setMovingSelection(false); }}>
        <div className="folder-picker-list">
          <button type="button" className="action-row" disabled={moveItems.isPending} onClick={() => moveItems.mutate(null)}><span><strong>Без папки</strong><small>Убрать текущую привязку</small></span></button>
          {folders.map((item) => <button type="button" className="action-row" key={item.id} disabled={moveItems.isPending} onClick={() => moveItems.mutate(item.id)}><span><strong>{item.name}</strong><small>{item.item_count} поз.</small></span></button>)}
        </div>
        {moveItems.error && <p className="form-error">{moveItems.error.message}</p>}
      </BottomSheet>

      <BottomSheet open={share !== null} title="Ссылка для обмена" onClose={() => setShare(null)}>
        {share && <div className="share-result">
          <div className="share-status"><span>Активна</span><small>до {new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long", year: "numeric" }).format(new Date(share.expires_at))}</small></div>
          <label className="share-link"><Link2 aria-hidden="true" /><span className="sr-only">Ссылка для обмена</span><input readOnly value={share.deep_link} onFocus={(event) => event.currentTarget.select()} /></label>
          {copyError && <p className="form-error" role="alert">{copyError}</p>}
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
