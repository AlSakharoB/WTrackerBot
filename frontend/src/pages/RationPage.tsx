import { Plus, Utensils } from "lucide-react";
import { useState } from "react";

import {
  DateSwitcher,
  EmptyState,
  MetricTile,
  ProgressBar,
} from "../components/ui";

export function RationPage() {
  const [date, setDate] = useState(() => new Date());
  return (
    <div className="page page--ration">
      <DateSwitcher value={date} onChange={setDate} />

      <section className="section-block" aria-labelledby="daily-summary-title">
        <div className="section-heading">
          <div>
            <h1 id="daily-summary-title">Итоги дня</h1>
            <p>Калории и макронутриенты</p>
          </div>
          <span className="summary-value">0 ккал</span>
        </div>
        <div className="metric-grid">
          <MetricTile
            label="Белки"
            value="0 г"
            detail="Цель не задана"
            tone="protein"
            footer={<ProgressBar label="Белки" value={0} tone="protein" />}
          />
          <MetricTile
            label="Жиры"
            value="0 г"
            detail="Цель не задана"
            tone="fat"
            footer={<ProgressBar label="Жиры" value={0} tone="fat" />}
          />
          <MetricTile
            label="Углеводы"
            value="0 г"
            detail="Цель не задана"
            tone="carbs"
            footer={<ProgressBar label="Углеводы" value={0} tone="carbs" />}
          />
        </div>
      </section>

      <section className="section-block" aria-labelledby="meals-title">
        <div className="section-heading">
          <div>
            <h2 id="meals-title">Приемы пищи</h2>
            <p>0 записей</p>
          </div>
          <button className="button-primary button-with-icon" type="button">
            <Plus aria-hidden="true" size={18} /> Добавить
          </button>
        </div>
        <EmptyState
          title="Рацион пока пуст"
          description="Добавьте первый прием пищи за выбранный день."
          icon={Utensils}
        />
      </section>
    </div>
  );
}
