import { WifiOff } from "lucide-react";

interface TopBarProps {
  title: string;
  subtitle?: string;
}

export function TopBar({ title, subtitle }: TopBarProps) {
  return (
    <header className="top-bar">
      <div className="brand-mark" aria-hidden="true">W</div>
      <div className="top-bar__titles">
        <span>{title}</span>
        {subtitle && <small>{subtitle}</small>}
      </div>
      {!navigator.onLine && (
        <span className="offline-indicator" title="Нет подключения">
          <WifiOff aria-hidden="true" size={18} />
          <span className="sr-only">Нет подключения</span>
        </span>
      )}
    </header>
  );
}
