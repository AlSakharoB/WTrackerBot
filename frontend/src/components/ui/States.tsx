import type { LucideIcon } from "lucide-react";
import { CircleAlert, Inbox } from "lucide-react";

interface EmptyStateProps {
  title: string;
  description?: string;
  action?: React.ReactNode;
  icon?: LucideIcon;
}

export function EmptyState({
  title,
  description,
  action,
  icon: Icon = Inbox,
}: EmptyStateProps) {
  return (
    <div className="empty-state">
      <span className="empty-state__icon"><Icon aria-hidden="true" /></span>
      <strong>{title}</strong>
      {description && <p>{description}</p>}
      {action}
    </div>
  );
}

interface ErrorStateProps {
  title?: string;
  message: string;
  onRetry?: () => void;
}

export function ErrorState({
  title = "Не удалось загрузить данные",
  message,
  onRetry,
}: ErrorStateProps) {
  return (
    <div className="empty-state" role="alert">
      <span className="empty-state__icon empty-state__icon--error">
        <CircleAlert aria-hidden="true" />
      </span>
      <strong>{title}</strong>
      <p>{message}</p>
      {onRetry && <button type="button" className="button-secondary" onClick={onRetry}>Повторить</button>}
    </div>
  );
}

export function Skeleton({ lines = 3 }: { lines?: number }) {
  return (
    <div className="skeleton" aria-busy="true" aria-label="Загрузка">
      <span className="sr-only">Загрузка данных</span>
      {Array.from({ length: lines }, (_, index) => (
        <span aria-hidden="true" key={index} />
      ))}
    </div>
  );
}
