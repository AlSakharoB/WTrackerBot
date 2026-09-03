import { Plus, Scale } from "lucide-react";
import { useState } from "react";

import { EmptyState, MetricTile, SegmentedControl } from "../components/ui";

type Period = "month" | "quarter" | "year";
const PERIODS = [
  { value: "month", label: "Месяц" },
  { value: "quarter", label: "3 месяца" },
  { value: "year", label: "Год" },
] as const;

export function WeightPage() {
  const [period, setPeriod] = useState<Period>("month");
  return (
    <div className="page page--weight">
      <section className="weight-overview" aria-labelledby="weight-summary-title">
        <div className="section-heading">
          <div>
            <h1 id="weight-summary-title">Текущий вес</h1>
            <p>Последняя запись</p>
          </div>
          <button className="button-primary button-with-icon" type="button">
            <Plus aria-hidden="true" size={18} /> Записать
          </button>
        </div>
        <div className="metric-grid metric-grid--weight">
          <MetricTile label="Вес" value="— кг" detail="Нет данных" />
          <MetricTile label="Цель" value="— кг" detail="Не задана" tone="protein" />
          <MetricTile label="Изменение" value="— кг" detail="За период" tone="carbs" />
        </div>
      </section>
      <section className="section-block" aria-labelledby="weight-chart-title">
        <div className="section-heading section-heading--stackable">
          <div>
            <h2 id="weight-chart-title">Динамика</h2>
            <p>История измерений</p>
          </div>
          <SegmentedControl
            label="Период графика"
            options={PERIODS}
            value={period}
            onChange={setPeriod}
          />
        </div>
        <div className="chart-empty">
          <div className="chart-grid" aria-hidden="true" />
          <EmptyState
            title="Недостаточно данных"
            description="Запишите вес, чтобы увидеть динамику."
            icon={Scale}
          />
        </div>
      </section>
    </div>
  );
}
