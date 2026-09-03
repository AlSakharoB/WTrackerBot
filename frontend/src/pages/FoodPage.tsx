import { FolderPlus, Plus, Search, Soup } from "lucide-react";
import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { BottomSheet, EmptyState, SegmentedControl } from "../components/ui";

type FoodKind = "ingredients" | "dishes";

const FOOD_OPTIONS = [
  { value: "ingredients", label: "Ингредиенты" },
  { value: "dishes", label: "Блюда" },
] as const;

export function FoodPage() {
  const [kind, setKind] = useState<FoodKind>("ingredients");
  const [query, setQuery] = useState("");
  const location = useLocation();
  const navigate = useNavigate();
  const sheetOpen = location.pathname === "/food/new";
  return (
    <div className="page">
      <SegmentedControl
        label="Тип еды"
        options={FOOD_OPTIONS}
        value={kind}
        onChange={setKind}
      />
      <div className="search-field">
        <Search aria-hidden="true" size={19} />
        <label className="sr-only" htmlFor="food-search">Поиск еды</label>
        <input
          id="food-search"
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder={kind === "ingredients" ? "Найти ингредиент" : "Найти блюдо"}
        />
      </div>
      <div className="toolbar-row">
        <button type="button" className="button-secondary button-with-icon">
          <FolderPlus aria-hidden="true" size={18} /> Папки
        </button>
        <button
          type="button"
          className="button-primary button-with-icon"
          onClick={() => navigate("/food/new")}
        >
          <Plus aria-hidden="true" size={18} /> Добавить
        </button>
      </div>
      <section className="section-block" aria-label="Список еды">
        <EmptyState
          title={query ? "Ничего не найдено" : kind === "ingredients" ? "Нет ингредиентов" : "Нет блюд"}
          description={query ? "Измените запрос и попробуйте снова." : "Добавленные продукты появятся здесь."}
          icon={Soup}
        />
      </section>
      <BottomSheet
        open={sheetOpen}
        title="Добавить еду"
        onClose={() => navigate("/food", { replace: true })}
      >
        <div className="action-list">
          <button type="button" className="action-row">Новый ингредиент</button>
          <button type="button" className="action-row">Новое блюдо</button>
        </div>
      </BottomSheet>
    </div>
  );
}
