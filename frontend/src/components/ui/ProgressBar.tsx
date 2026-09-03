interface ProgressBarProps {
  value: number;
  max?: number;
  label: string;
  tone?: "protein" | "fat" | "carbs" | "energy";
}

export function ProgressBar({
  value,
  max = 100,
  label,
  tone = "energy",
}: ProgressBarProps) {
  const safeMax = max > 0 ? max : 100;
  const percent = Math.min(100, Math.max(0, (value / safeMax) * 100));
  return (
    <div
      className={`progress progress--${tone}`}
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={safeMax}
      aria-valuenow={Math.min(safeMax, Math.max(0, value))}
    >
      <span style={{ width: `${percent}%` }} />
    </div>
  );
}
