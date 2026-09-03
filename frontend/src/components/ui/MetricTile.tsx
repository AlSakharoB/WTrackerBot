import type { ReactNode } from "react";

interface MetricTileProps {
  label: string;
  value: string;
  detail?: string;
  tone?: "protein" | "fat" | "carbs" | "energy";
  footer?: ReactNode;
}

export function MetricTile({
  label,
  value,
  detail,
  tone = "energy",
  footer,
}: MetricTileProps) {
  return (
    <article className={`metric-tile metric-tile--${tone}`}>
      <span className="metric-tile__label">{label}</span>
      <strong>{value}</strong>
      {detail && <span className="metric-tile__detail">{detail}</span>}
      {footer}
    </article>
  );
}
