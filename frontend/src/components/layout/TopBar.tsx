import { WifiOff } from "lucide-react";
import { useEffect, useState } from "react";

interface TopBarProps {
  title: string;
  subtitle?: string;
}

export function TopBar({ title, subtitle }: TopBarProps) {
  const [online, setOnline] = useState(() => navigator.onLine);

  useEffect(() => {
    const handleOnline = () => setOnline(true);
    const handleOffline = () => setOnline(false);
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);
    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, []);

  return (
    <header className="top-bar">
      <div className="brand-mark" aria-hidden="true">W</div>
      <div className="top-bar__titles">
        <strong>WTracker</strong>
        <small>{title}{subtitle ? ` · ${subtitle}` : ""}</small>
      </div>
      <span
        className={`connection-status ${online ? "is-online" : "is-offline"}`}
        role="status"
      >
        {online ? <i aria-hidden="true" /> : <WifiOff aria-hidden="true" />}
        <span>{online ? "В сети" : "Нет сети"}</span>
      </span>
    </header>
  );
}
