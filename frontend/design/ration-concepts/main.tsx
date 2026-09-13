import {
  Apple,
  Bell,
  CalendarDays,
  ChartNoAxesColumnIncreasing,
  Check,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  CirclePlus,
  Clock3,
  CookingPot,
  Download,
  Flame,
  Folder,
  FolderOpen,
  Globe2,
  Minus,
  MoonStar,
  MoreVertical,
  MoveHorizontal,
  PackageCheck,
  Palette,
  Plus,
  RotateCcw,
  ScanBarcode,
  Search,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  SunMedium,
  Sunrise,
  Target,
  Trash2,
  UserRound,
  Utensils,
  X,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { createRoot } from "react-dom/client";

import "./styles.css";

type Concept = "a" | "b";
type Theme = "light" | "dark";
type Page = "ration" | "food" | "weight" | "profile" | "barcode";

const params = new URLSearchParams(window.location.search);
const selectedDirection = params.get("concept") === "selected";
const concept: Concept = params.get("concept") === "b" ? "b" : "a";
const theme: Theme = params.get("theme") === "dark" ? "dark" : "light";
const showSheet = params.get("sheet") === "1";
const requestedPage = params.get("page");
const selectedPage: Page = requestedPage === "food" || requestedPage === "weight" || requestedPage === "profile" || requestedPage === "barcode" ? requestedPage : "ration";

document.documentElement.dataset.theme = theme;
document.documentElement.style.colorScheme = theme;

const macros = [
  { key: "protein", short: "Б", label: "Белки", value: "74", target: "80", percent: 93, excess: false },
  { key: "fat", short: "Ж", label: "Жиры", value: "33", target: "25", percent: 133, excess: true },
  { key: "carbs", short: "У", label: "Углеводы", value: "149", target: "130", percent: 115, excess: true },
] as const;

const navItems = [
  { id: "ration", label: "Рацион", icon: Utensils },
  { id: "food", label: "Еда", icon: Apple },
  { id: "weight", label: "Вес", icon: ChartNoAxesColumnIncreasing },
  { id: "profile", label: "Профиль", icon: UserRound },
] as const;

function IconButton({ label, children, quiet = false }: { label: string; children: React.ReactNode; quiet?: boolean }) {
  return <button className={quiet ? "icon-button is-quiet" : "icon-button"} type="button" aria-label={label}>{children}</button>;
}

function TopBar() {
  return (
    <header className="top-bar">
      <div className="brand-mark" aria-hidden="true">W</div>
      <div className="brand-copy"><strong>WTracker</strong><span>Дневник питания</span></div>
      <span className="sync-state"><span aria-hidden="true" />Сохранено</span>
    </header>
  );
}

function DateBar({ analytical = false }: { analytical?: boolean }) {
  return (
    <section className={analytical ? "date-bar date-bar--analytical" : "date-bar"} aria-label="Выбранная дата">
      <IconButton label="Предыдущий день" quiet><ChevronLeft aria-hidden="true" /></IconButton>
      <div>
        <strong>{analytical ? "Рацион сегодня" : "Сегодня"}</strong>
        <span>13 сентября, воскресенье</span>
      </div>
      <IconButton label="Следующий день" quiet><ChevronRight aria-hidden="true" /></IconButton>
    </section>
  );
}

function BottomNavigation({ active = "ration" }: { active?: Page }) {
  return (
    <nav className="bottom-nav" aria-label="Основные разделы">
      {navItems.map(({ id, label, icon: Icon }) => (
        <button className={id === active ? "is-active" : ""} type="button" key={label} aria-current={id === active ? "page" : undefined}>
          <Icon aria-hidden="true" />
          <span>{label}</span>
        </button>
      ))}
    </nav>
  );
}

function MacroRail() {
  return (
    <div className="macro-rail" aria-label="Белки, жиры и углеводы">
      {macros.map((macro) => (
        <div className={`macro-cell macro-${macro.key}`} key={macro.key}>
          <div><span>{macro.short}</span><strong>{macro.value}<small> / {macro.target} г</small></strong></div>
          <div className="micro-progress"><i style={{ width: `${Math.min(macro.percent, 100)}%` }} /></div>
          <b className={macro.excess ? "is-excess" : ""}>{macro.percent}%</b>
        </div>
      ))}
    </div>
  );
}

function EntryRow({ dish, name, grams, kcal }: { dish?: boolean; name: string; grams: string; kcal: string }) {
  const Icon = dish ? CookingPot : Apple;
  return (
    <div className="entry-row">
      <span className="entry-kind"><Icon aria-hidden="true" /></span>
      <div className="entry-name"><strong>{name}</strong><span>{grams}</span></div>
      <strong className="entry-kcal">{kcal}<small> ккал</small></strong>
    </div>
  );
}

function CompactMeal({ type, title, summary, children, empty = false }: { type: string; title: string; summary: string; children?: React.ReactNode; empty?: boolean }) {
  const Icon = type === "breakfast" ? Sunrise : type === "lunch" ? SunMedium : type === "snack" ? Apple : MoonStar;
  return (
    <article className={`compact-meal meal-${type}`}>
      <header>
        <span className="meal-symbol"><Icon aria-hidden="true" /></span>
        <div><strong>{title}</strong><span>{summary}</span></div>
        <IconButton label={`Добавить в ${title.toLowerCase()}`} quiet><Plus aria-hidden="true" /></IconButton>
      </header>
      {empty ? (
        <button className="empty-meal-action" type="button"><span>Пока пусто</span><strong>Добавить еду</strong></button>
      ) : <div className="entry-list">{children}</div>}
    </article>
  );
}

function ConceptA() {
  return (
    <div className="app concept-a">
      <TopBar />
      <main>
        <DateBar />
        <section className="daily-ledger" aria-labelledby="concept-a-title">
          <div className="ledger-heading">
            <div><span>Итог дня</span><h1 id="concept-a-title">1 176 <small>ккал</small></h1></div>
            <div className="goal-alert"><Flame aria-hidden="true" /><span>Цель 1 000 ккал<strong>+176 ккал</strong></span></div>
          </div>
          <div className="energy-progress" aria-label="Калории: 118 процентов от цели"><i /></div>
          <div className="energy-caption"><span>0</span><strong>118% · цель превышена</strong><span>1 000</span></div>
          <MacroRail />
        </section>

        <section className="meal-ledger" aria-labelledby="meals-a-title">
          <header className="section-title"><div><h2 id="meals-a-title">Приёмы пищи</h2><span>5 записей</span></div><button type="button" className="primary-icon"><Plus aria-hidden="true" /><span>Добавить</span></button></header>
          <CompactMeal type="breakfast" title="Завтрак" summary="460 ккал · Б 20 · Ж 11 · У 72">
            <EntryRow dish name="Овсянка с йогуртом и бананом" grams="300 г" kcal="367" />
          </CompactMeal>
          <CompactMeal type="lunch" title="Обед" summary="627 ккал · Б 54 · Ж 22 · У 54">
            <EntryRow name="Творог 5% и цельнозерновой хлеб" grams="380 г" kcal="627" />
          </CompactMeal>
          <CompactMeal type="dinner" title="Ужин" summary="0 ккал" empty />
        </section>
      </main>
      <BottomNavigation />
      {showSheet && <AddSheetA />}
    </div>
  );
}

function NutritionRing() {
  return (
    <div className="nutrition-ring" role="img" aria-label="Белки 25 процентов, жиры 25 процентов, углеводы 50 процентов">
      <div><strong>1 176</strong><span>из 1 000 ккал</span></div>
    </div>
  );
}

function ConceptBMeal({ icon: Icon, title, kcal, meta, empty = false }: { icon: typeof Sunrise; title: string; kcal: string; meta: string; empty?: boolean }) {
  return (
    <article className={`timeline-meal${empty ? " is-empty" : ""}`}>
      <span className="timeline-icon"><Icon aria-hidden="true" /></span>
      <div className="timeline-copy"><div><strong>{title}</strong><b>{kcal} ккал</b></div><span>{meta}</span></div>
      <IconButton label={`Добавить в ${title.toLowerCase()}`} quiet><CirclePlus aria-hidden="true" /></IconButton>
    </article>
  );
}

function ConceptB() {
  return (
    <div className="app concept-b">
      <TopBar />
      <main>
        <DateBar analytical />
        <section className="balance-board" aria-labelledby="concept-b-title">
          <div className="balance-title"><div><span>Баланс дня</span><h1 id="concept-b-title">Цель превышена</h1></div><span className="over-badge">+176 ккал</span></div>
          <div className="balance-content">
            <NutritionRing />
            <div className="macro-legend">
              {macros.map((macro) => <div className={`macro-${macro.key}`} key={macro.key}><i /><span>{macro.label}<small>{macro.percent}%</small></span><strong>{macro.value}<small> / {macro.target} г</small></strong></div>)}
            </div>
          </div>
        </section>

        <section className="timeline" aria-labelledby="meals-b-title">
          <header className="section-title"><div><h2 id="meals-b-title">Сегодня</h2><span>По приёмам пищи</span></div><button type="button" className="primary-icon"><Plus aria-hidden="true" /><span>Добавить</span></button></header>
          <div className="timeline-list">
            <ConceptBMeal icon={Sunrise} title="Завтрак" kcal="460" meta="2 записи · Б 20 · Ж 11 · У 72" />
            <ConceptBMeal icon={SunMedium} title="Обед" kcal="627" meta="2 записи · Б 54 · Ж 22 · У 54" />
            <ConceptBMeal icon={MoonStar} title="Ужин" kcal="0" meta="Пока ничего не добавлено" empty />
          </div>
        </section>
      </main>
      <BottomNavigation />
      {showSheet && <AddSheetB />}
    </div>
  );
}

function SelectedMeals() {
  return (
    <section className="meal-ledger selected-meals" aria-labelledby="selected-meals-title">
      <header className="section-title"><div><h2 id="selected-meals-title">Приёмы пищи</h2><span>5 записей</span></div><button type="button" className="primary-icon"><Plus aria-hidden="true" /><span>Добавить</span></button></header>
      <div className="selected-meal-grid">
        <CompactMeal type="breakfast" title="Завтрак" summary="460 ккал · Б 20 · Ж 11 · У 72">
          <EntryRow dish name="Овсянка с йогуртом и бананом" grams="300 г" kcal="367" />
        </CompactMeal>
        <CompactMeal type="lunch" title="Обед" summary="627 ккал · Б 54 · Ж 22 · У 54">
          <EntryRow name="Творог 5% и цельнозерновой хлеб" grams="380 г" kcal="627" />
        </CompactMeal>
        <CompactMeal type="dinner" title="Ужин" summary="0 ккал" empty />
        <CompactMeal type="snack" title="Перекус" summary="88 ккал · Б 1 · Ж 0 · У 24">
          <EntryRow name="Яблоко зелёное" grams="170 г" kcal="88" />
        </CompactMeal>
      </div>
    </section>
  );
}

function SelectedRation() {
  return (
    <div className="app concept-a selected-ration">
      <TopBar />
      <main>
        <DateBar />
        <div className="selected-layout">
          <section className="hybrid-summary" aria-labelledby="hybrid-summary-title">
            <div className="hybrid-heading"><div><span>Итог дня</span><h1 id="hybrid-summary-title">Баланс КБЖУ</h1></div><div className="hybrid-excess"><Flame aria-hidden="true" /><span>Цель превышена<strong>+176 ккал</strong></span></div></div>
            <div className="hybrid-content">
              <NutritionRing />
              <div className="macro-legend hybrid-legend">
                {macros.map((macro) => <div className={`macro-${macro.key}`} key={macro.key}><i /><span>{macro.label}<small>{macro.percent}%</small></span><strong>{macro.value}<small> / {macro.target} г</small></strong></div>)}
              </div>
            </div>
            <div className="hybrid-energy"><span>Калории</span><div><i /></div><strong>1 176 / 1 000 <small>ккал</small></strong><b>118%</b></div>
          </section>
          <SelectedMeals />
        </div>
      </main>
      <BottomNavigation />
    </div>
  );
}

function SheetFrame({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="sheet-layer">
      <div className="scrim" />
      <section className="add-sheet" role="dialog" aria-modal="true" aria-labelledby="add-sheet-title">
        <div className="sheet-handle" />
        <header><div><span>Сегодня · Завтрак</span><h2 id="add-sheet-title">{title}</h2></div><IconButton label="Закрыть" quiet><X aria-hidden="true" /></IconButton></header>
        {children}
      </section>
    </div>
  );
}

function AddSheetA() {
  const recent = [
    ["Овсянка с йогуртом и бананом", "370 ккал / 100 г", "Блюдо"],
    ["Йогурт натуральный 2,5%", "62 ккал / 100 г", "Ингредиент"],
    ["Банан", "89 ккал / 100 г", "Ингредиент"],
  ];
  return (
    <SheetFrame title="Добавить еду">
      <div className="search-box"><Search aria-hidden="true" /><span>Найти ингредиент или блюдо</span></div>
      <div className="sheet-tabs" role="tablist"><button className="is-active" type="button">Все</button><button type="button">Ингредиенты</button><button type="button">Блюда</button></div>
      <div className="recent-heading"><strong>Недавние</strong><span>Часто используемые</span></div>
      <div className="source-list">
        {recent.map(([name, kcal, type]) => <button type="button" key={name}><span className="source-icon">{type === "Блюдо" ? <CookingPot aria-hidden="true" /> : <Apple aria-hidden="true" />}</span><span><strong>{name}</strong><small>{type} · {kcal}</small></span><Plus aria-hidden="true" /></button>)}
      </div>
      <button className="secondary-action" type="button"><CalendarDays aria-hidden="true" />Выбрать другой приём пищи</button>
    </SheetFrame>
  );
}

function AddSheetB() {
  return (
    <SheetFrame title="Порция и приём пищи">
      <div className="selected-food">
        <span className="selected-icon"><CookingPot aria-hidden="true" /></span>
        <div><span>Выбрано блюдо</span><strong>Овсянка с йогуртом и бананом</strong><small>370 ккал на 100 г</small></div>
        <span className="selected-check"><Check aria-hidden="true" /></span>
      </div>
      <div className="meal-picker" role="group" aria-label="Приём пищи">
        {[["Завтрак", Sunrise], ["Обед", SunMedium], ["Ужин", MoonStar]].map(([label, Icon], index) => <button className={index === 0 ? "is-active" : ""} type="button" key={label as string}><Icon aria-hidden="true" /><span>{label as string}</span></button>)}
      </div>
      <div className="portion-editor">
        <div><span>Размер порции</span><strong>300 <small>г</small></strong></div>
        <div className="stepper"><IconButton label="Уменьшить"><Minus aria-hidden="true" /></IconButton><span>300</span><IconButton label="Увеличить"><Plus aria-hidden="true" /></IconButton></div>
      </div>
      <div className="portion-macros"><div><span>Ккал</span><strong>1 110</strong></div><div><span>Белки</span><strong>58,8 г</strong></div><div><span>Жиры</span><strong>33,9 г</strong></div><div><span>Углеводы</span><strong>214,5 г</strong></div></div>
      <button className="save-action" type="button"><Check aria-hidden="true" />Добавить в завтрак</button>
    </SheetFrame>
  );
}

const foodItems = [
  { type: "ingredient", name: "Йогурт натуральный 2,5%", meta: "62 ккал · Б 4 · Ж 2,5 · У 5,9", folder: "Молочные" },
  { type: "ingredient", name: "Банан", meta: "89 ккал · Б 1,1 · Ж 0,3 · У 23", folder: "Фрукты" },
  { type: "dish", name: "Овсянка с йогуртом и бананом", meta: "370 ккал · Б 19,6 · Ж 11,3 · У 71,5", folder: "Завтраки" },
  { type: "ingredient", name: "Хлеб цельнозерновой с семенами", meta: "250 ккал · Б 9 · Ж 4 · У 44", folder: "Без папки" },
] as const;

function PageTitle({ eyebrow, title, children }: { eyebrow: string; title: string; children?: React.ReactNode }) {
  return <header className="page-title"><div><span>{eyebrow}</span><h1>{title}</h1></div><div className="page-actions">{children}</div></header>;
}

function CatalogItem({ item, library = false }: { item: typeof foodItems[number]; library?: boolean }) {
  const ItemIcon = item.type === "dish" ? CookingPot : Apple;
  return (
    <article className={library ? "library-item" : "catalog-item"}>
      <span className="catalog-icon"><ItemIcon aria-hidden="true" /></span>
      <div className="catalog-copy"><strong>{item.name}</strong><span>{item.meta} / 100 г</span>{library && <small><Folder aria-hidden="true" />{item.folder}</small>}</div>
      {!library && <span className="folder-label">{item.folder}</span>}
      <IconButton label={`Действия: ${item.name}`} quiet><MoreVertical aria-hidden="true" /></IconButton>
    </article>
  );
}

function FoodConcept({ direction }: { direction: Concept }) {
  const isA = direction === "a";
  return (
    <div className={`app concept-${direction} food-concept food-concept-${direction}`}>
      <TopBar />
      <main>
        <PageTitle eyebrow={isA ? "Каталог · 24 позиции" : "Моя коллекция"} title={isA ? "Еда" : "Продукты и блюда"}>
          <IconButton label="Сканировать штрихкод"><ScanBarcode aria-hidden="true" /></IconButton>
          <button className="primary-icon" type="button"><Plus aria-hidden="true" /><span>Добавить</span></button>
        </PageTitle>
        {isA ? <FoodDirectionA /> : <FoodDirectionB />}
      </main>
      <BottomNavigation active="food" />
    </div>
  );
}

function FoodDirectionA() {
  return (
    <>
      <div className="catalog-search"><Search aria-hidden="true" /><span>Найти продукт или блюдо</span><IconButton label="Фильтры" quiet><SlidersHorizontal aria-hidden="true" /></IconButton></div>
      <div className="catalog-tabs" role="tablist"><button className="is-active" type="button">Ингредиенты <span>18</span></button><button type="button">Блюда <span>6</span></button></div>
      <div className="folder-strip" aria-label="Папки">
        <button className="is-active" type="button"><FolderOpen aria-hidden="true" />Все</button>
        <button type="button"><Folder aria-hidden="true" />Фрукты</button>
        <button type="button"><Folder aria-hidden="true" />Молочные</button>
        <IconButton label="Управлять папками"><Settings2 aria-hidden="true" /></IconButton>
      </div>
      <section className="catalog-list" aria-label="Ингредиенты">
        {foodItems.slice(0, 3).map((item) => <CatalogItem item={item} key={item.name} />)}
      </section>
    </>
  );
}

function FoodDirectionB() {
  return (
    <>
      <div className="library-search"><Search aria-hidden="true" /><span>Поиск по всей коллекции</span></div>
      <section className="collections" aria-labelledby="collections-title">
        <div className="subsection-heading"><h2 id="collections-title">Папки</h2><button type="button">Управлять</button></div>
        <div className="collection-grid">
          <button type="button"><span className="collection-icon fruit"><Apple aria-hidden="true" /></span><strong>Фрукты</strong><small>5 продуктов</small></button>
          <button type="button"><span className="collection-icon dairy"><Folder aria-hidden="true" /></span><strong>Молочные</strong><small>4 продукта</small></button>
          <button type="button"><span className="collection-icon breakfast"><Sunrise aria-hidden="true" /></span><strong>Завтраки</strong><small>3 блюда</small></button>
        </div>
      </section>
      <section className="library-list" aria-labelledby="recent-food-title">
        <div className="subsection-heading"><div><h2 id="recent-food-title">Недавние</h2><span>Сначала часто используемые</span></div><IconButton label="Сортировка" quiet><SlidersHorizontal aria-hidden="true" /></IconButton></div>
        {foodItems.slice(0, 3).map((item) => <CatalogItem item={item} library key={item.name} />)}
      </section>
    </>
  );
}

function WeightPlot({ spacious = false }: { spacious?: boolean }) {
  return (
    <div className={spacious ? "weight-plot is-spacious" : "weight-plot"}>
      <div className="chart-tooltip"><strong>78,4 кг</strong><span>13 сентября · 08:10</span></div>
      <svg viewBox="0 0 342 166" role="img" aria-label="Вес снизился с 80,1 до 78,4 килограмма. Среднее за 7 дней 78,8 килограмма. Цель 74 килограмма.">
        <title>Динамика веса за 30 дней</title>
        <g className="chart-grid"><path d="M28 28H332M28 70H332M28 112H332M28 148H332" /><path d="M28 18V148" /></g>
        <g className="chart-labels"><text x="2" y="32">80</text><text x="2" y="74">78</text><text x="2" y="116">76</text><text x="2" y="152">74</text><text x="28" y="163">15 авг</text><text x="290" y="163">13 сен</text></g>
        <path className="goal-line" d="M28 148H332" />
        <path className="average-line" d="M28 35C66 36 92 41 124 45S184 51 220 55S281 59 332 61" />
        <path className="actual-line" d="M28 30L50 34L72 31L94 43L116 40L138 52L160 48L182 59L204 56L226 66L248 61L270 71L292 66L332 67" />
        <g className="chart-points"><circle cx="28" cy="30" r="4" /><circle cx="94" cy="43" r="4" /><circle cx="160" cy="48" r="4" /><circle cx="226" cy="66" r="4" /><circle cx="292" cy="66" r="4" /><circle className="is-selected" cx="332" cy="67" r="6" /></g>
      </svg>
      <div className="chart-legend"><span><i className="actual" />Вес</span><span><i className="average" />Среднее 7 дней</span><span><i className="goal" />Цель</span></div>
    </div>
  );
}

function RangeControls() {
  return (
    <div className="range-controls">
      <div role="group" aria-label="Период"><button type="button">7</button><button className="is-active" type="button">30</button><button type="button">90</button><button type="button">365</button></div>
      <div><IconButton label="Предыдущий период"><ChevronLeft aria-hidden="true" /></IconButton><IconButton label="Следующий период"><ChevronRight aria-hidden="true" /></IconButton><IconButton label="Уменьшить масштаб"><ZoomOut aria-hidden="true" /></IconButton><IconButton label="Увеличить масштаб"><ZoomIn aria-hidden="true" /></IconButton><IconButton label="Текущий период"><RotateCcw aria-hidden="true" /></IconButton></div>
    </div>
  );
}

function WeightConcept({ direction }: { direction: Concept }) {
  const isA = direction === "a";
  return (
    <div className={`app concept-${direction} weight-concept weight-concept-${direction}`}>
      <TopBar />
      <main>
        <PageTitle eyebrow="Последнее измерение · сегодня" title="Вес">
          <button className="primary-icon" type="button"><Plus aria-hidden="true" /><span>Записать</span></button>
        </PageTitle>
        {isA ? <WeightDirectionA /> : <WeightDirectionB />}
      </main>
      <BottomNavigation active="weight" />
    </div>
  );
}

function WeightDirectionA() {
  return (
    <>
      <section className="weight-metrics" aria-label="Сводка веса">
        <div><span>Сейчас</span><strong>78,4 <small>кг</small></strong><b className="positive">−1,7 кг</b></div>
        <div><span>Среднее 7 дней</span><strong>78,8 <small>кг</small></strong><b>−0,4 кг</b></div>
        <div><span>До цели</span><strong>4,4 <small>кг</small></strong><b>цель 74 кг</b></div>
      </section>
      <section className="weight-panel" aria-labelledby="weight-a-chart">
        <div className="weight-panel-title"><div><h2 id="weight-a-chart">Динамика</h2><span>15 августа — 13 сентября</span></div><span><MoveHorizontal aria-hidden="true" />Листайте график</span></div>
        <WeightPlot />
        <RangeControls />
      </section>
      <div className="weight-history-preview"><span><Clock3 aria-hidden="true" /></span><div><strong>Сегодня, 08:10</strong><small>Утреннее измерение</small></div><b>78,4 кг</b><ChevronRight aria-hidden="true" /></div>
    </>
  );
}

function WeightDirectionB() {
  return (
    <>
      <section className="weight-status">
        <div><span>Текущий вес</span><strong>78,4 <small>кг</small></strong><b>−0,4 кг за неделю</b></div>
        <div className="goal-progress-ring"><span>55%</span><small>до цели</small></div>
        <div className="goal-copy"><Target aria-hidden="true" /><span>Цель<strong>74 кг</strong><small>осталось 4,4 кг</small></span></div>
      </section>
      <section className="weight-stage" aria-labelledby="weight-b-chart">
        <div className="weight-stage-heading"><div><h2 id="weight-b-chart">Последние 30 дней</h2><span>15 августа — 13 сентября</span></div><span className="window-badge">30 дней</span></div>
        <WeightPlot spacious />
        <div className="gesture-note"><MoveHorizontal aria-hidden="true" /><span>Проведите по графику для просмотра истории</span></div>
        <RangeControls />
      </section>
    </>
  );
}

const profileRows = [
  { icon: Palette, title: "Оформление", value: "Как в Telegram" },
  { icon: Globe2, title: "Часовой пояс", value: "Europe/Moscow" },
  { icon: Bell, title: "Напоминания", value: "2 активных" },
  { icon: Settings2, title: "После добавления еды", value: "Вернуться в рацион" },
] as const;

function SettingsRow({ row }: { row: typeof profileRows[number] }) {
  const RowIcon = row.icon;
  return <button className="settings-row" type="button"><span><RowIcon aria-hidden="true" /></span><div><strong>{row.title}</strong><small>{row.value}</small></div><ChevronRight aria-hidden="true" /></button>;
}

function ProfileIdentity({ minimal = false }: { minimal?: boolean }) {
  return <section className={minimal ? "profile-identity is-minimal" : "profile-identity"}><span className="profile-avatar">А</span><div><strong>Алексей</strong><span>@alexey · данные синхронизированы</span></div>{!minimal && <span className="profile-ok"><CheckCircle2 aria-hidden="true" />Активен</span>}</section>;
}

function GoalGrid() {
  return <div className="goal-grid"><div className="energy"><span>Ккал</span><strong>1 000</strong></div><div className="protein"><span>Белки</span><strong>80 г</strong></div><div className="fat"><span>Жиры</span><strong>25 г</strong></div><div className="carbs"><span>Углеводы</span><strong>130 г</strong></div></div>;
}

function ProfileConcept({ direction }: { direction: Concept }) {
  const isA = direction === "a";
  return (
    <div className={`app concept-${direction} profile-concept profile-concept-${direction}`}>
      <TopBar />
      <main>
        {isA && <PageTitle eyebrow="Аккаунт и настройки" title="Профиль" />}
        {isA ? <ProfileDirectionA /> : <ProfileDirectionB />}
      </main>
      <BottomNavigation active="profile" />
    </div>
  );
}

function ProfileDirectionA() {
  return (
    <>
      <ProfileIdentity />
      <section className="settings-group" aria-labelledby="profile-goals-a"><div className="subsection-heading"><div><h2 id="profile-goals-a">Цели питания</h2><span>Дневные значения</span></div><button type="button">Изменить</button></div><GoalGrid /></section>
      <section className="settings-group settings-list" aria-labelledby="settings-a"><div className="subsection-heading"><h2 id="settings-a">Настройки</h2></div>{profileRows.slice(0, 3).map((row) => <SettingsRow row={row} key={row.title} />)}</section>
      <div className="profile-data-actions"><button type="button"><Download aria-hidden="true" />Экспорт</button><button type="button"><ShieldCheck aria-hidden="true" />Приватность</button></div>
    </>
  );
}

function ProfileDirectionB() {
  return (
    <>
      <header className="profile-heading-b"><span>Ваши данные</span><h1>Профиль</h1></header>
      <ProfileIdentity minimal />
      <section className="preference-board">
        <div className="preference-heading"><div><span>Сегодня</span><h2>Цели питания</h2></div><button type="button">Настроить</button></div>
        <GoalGrid />
      </section>
      <section className="profile-modules" aria-label="Настройки профиля">
        <button type="button"><span className="module-icon"><Bell aria-hidden="true" /></span><span><strong>Напоминания</strong><small>Питание в 08:00 · вес по понедельникам</small></span><ChevronRight aria-hidden="true" /></button>
        <button type="button"><span className="module-icon"><Palette aria-hidden="true" /></span><span><strong>Интерфейс</strong><small>Тема Telegram · формат чисел авто</small></span><ChevronRight aria-hidden="true" /></button>
        <button type="button"><span className="module-icon"><ShieldCheck aria-hidden="true" /></span><span><strong>Данные и приватность</strong><small>Экспорт · политика · удаление данных</small></span><ChevronRight aria-hidden="true" /></button>
      </section>
      <footer className="profile-version"><span>WTrackerBot 0.4.7</span><button type="button"><Trash2 aria-hidden="true" />Удалить данные</button></footer>
    </>
  );
}

function BarcodeReview() {
  return (
    <div className="app concept-a barcode-review-concept">
      <TopBar />
      <main>
        <PageTitle eyebrow="Штрихкод · 4601234567890" title="Проверка продукта">
          <IconButton label="Закрыть"><X aria-hidden="true" /></IconButton>
        </PageTitle>
        <section className="off-status"><PackageCheck aria-hidden="true" /><div><strong>Продукт найден</strong><span>Данные получены из Open Food Facts</span></div><span>OFF</span></section>
        <section className="product-review" aria-labelledby="review-product-name">
          <div className="product-identity">
            <div className="product-photo"><img src="/design/ration-concepts/assets/yogurt-cup.png" alt="Белый стаканчик натурального йогурта с зелёной этикеткой" /></div>
            <div><span>Без бренда</span><h1 id="review-product-name">Йогурт натуральный 2,5%</h1><p>Стакан · масса упаковки 150 г</p><a href="https://world.openfoodfacts.org/" target="_blank" rel="noreferrer">Открыть источник</a></div>
          </div>
          <div className="derived-notice"><Sparkles aria-hidden="true" /><span><strong>Калорийность рассчитана</strong><small>Проверьте значение перед сохранением</small></span></div>
          <div className="review-heading"><div><strong>На 100 грамм</strong><span>Можно исправить вручную</span></div><button type="button">Изменить</button></div>
          <div className="review-macros"><div className="energy"><span>Ккал</span><strong>62</strong></div><div className="protein"><span>Белки</span><strong>4 г</strong></div><div className="fat"><span>Жиры</span><strong>2,5 г</strong></div><div className="carbs"><span>Углеводы</span><strong>5,9 г</strong></div></div>
          <label className="confirmation-row"><input type="checkbox" defaultChecked /><span><strong>Фото и данные соответствуют продукту</strong><small>Ингредиент будет доступен только вам</small></span></label>
        </section>
        <div className="review-actions"><button className="secondary-action" type="button"><ScanBarcode aria-hidden="true" />Сканировать снова</button><button className="save-action" type="button"><Check aria-hidden="true" />Создать ингредиент</button></div>
      </main>
      <BottomNavigation active="food" />
    </div>
  );
}

function App() {
  if (selectedDirection && selectedPage === "barcode") return <BarcodeReview />;
  if (selectedDirection && selectedPage === "ration") return <SelectedRation />;
  if (selectedDirection && selectedPage === "food") return <FoodConcept direction="a" />;
  if (selectedDirection && selectedPage === "weight") return <WeightConcept direction="a" />;
  if (selectedDirection && selectedPage === "profile") return <ProfileConcept direction="a" />;
  if (selectedPage === "food") return <FoodConcept direction={concept} />;
  if (selectedPage === "weight") return <WeightConcept direction={concept} />;
  if (selectedPage === "profile") return <ProfileConcept direction={concept} />;
  return concept === "a" ? <ConceptA /> : <ConceptB />;
}

createRoot(document.getElementById("root")!).render(<App />);
document.documentElement.classList.add("prototype-ready");
