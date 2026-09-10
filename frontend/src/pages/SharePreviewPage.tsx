import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CheckCircle2, CookingPot, Download, Salad } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import {
  fetchSharingPreview,
  importSharingPackage,
  type SharingIngredientPreview,
} from "../api/client";
import { useMiniAppContext } from "../app/context";
import { ErrorState, Skeleton, useToast } from "../components/ui";

function display(value: string): string {
  return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 }).format(Number(value));
}

function IngredientRow({ item }: { item: SharingIngredientPreview }) {
  const nutrition = item.nutrition_per_100g;
  return (
    <div className="share-preview-row">
      <Salad aria-hidden="true" />
      <div>
        <strong>{item.name}</strong>
        <span>{display(nutrition.energy_kcal)} ккал · Б {display(nutrition.protein_g)} · Ж {display(nutrition.fat_g)} · У {display(nutrition.carbs_g)}</span>
        {item.existing && <small>Будет использован «{item.existing.name}»</small>}
      </div>
    </div>
  );
}

export function SharePreviewPage() {
  const { token = "" } = useParams();
  const { initData } = useMiniAppContext();
  const queryClient = useQueryClient();
  const { showToast } = useToast();
  const preview = useQuery({
    queryKey: ["sharing-preview", token],
    queryFn: () => fetchSharingPreview(initData, token),
    enabled: Boolean(initData && token),
    retry: false,
  });
  const importMutation = useMutation({
    mutationFn: () => importSharingPackage(initData, token, preview.data!),
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({ queryKey: ["food"] });
      await preview.refetch();
      showToast(result.already_imported ? "Пакет уже импортирован" : "Пакет импортирован");
    },
  });

  return (
    <div className="page share-preview-page">
      <Link className="back-link" to="/food"><ArrowLeft aria-hidden="true" />Каталог еды</Link>
      {preview.isPending ? (
        <Skeleton lines={7} />
      ) : preview.error ? (
        <ErrorState title="Ссылка недоступна" message={preview.error.message} onRetry={() => void preview.refetch()} />
      ) : preview.data ? (
        <>
          <header className="share-preview-heading">
            <span>{preview.data.type === "dishes" ? <CookingPot aria-hidden="true" /> : <Salad aria-hidden="true" />}</span>
            <div><h1>{preview.data.type === "dishes" ? "Пакет блюд" : "Пакет ингредиентов"}</h1><p>{preview.data.item_count} элементов</p></div>
          </header>
          <section className="share-preview-list" aria-label="Содержимое пакета">
            {preview.data.dishes.map((dish) => <div className="share-preview-row" key={dish.key}><CookingPot aria-hidden="true" /><div><strong>{dish.name}</strong>{dish.conflict_type !== "new" && <small>Будет создана копия</small>}</div></div>)}
            {preview.data.ingredients.map((ingredient) => <IngredientRow key={ingredient.key} item={ingredient} />)}
          </section>
          {preview.data.already_imported ? (
            <div className="import-complete"><CheckCircle2 aria-hidden="true" /><span>Пакет уже импортирован</span></div>
          ) : preview.data.is_owner ? (
            <p className="form-error">Нельзя импортировать собственную ссылку.</p>
          ) : (
            <button type="button" className="button-primary button-with-icon import-button" disabled={importMutation.isPending} onClick={() => importMutation.mutate()}><Download aria-hidden="true" />{importMutation.isPending ? "Импортируем..." : "Импортировать"}</button>
          )}
          {importMutation.error && <p className="form-error">{importMutation.error.message}</p>}
        </>
      ) : null}
    </div>
  );
}
