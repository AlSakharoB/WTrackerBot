import { CircleCheck, CircleX, X } from "lucide-react";
import {
  useCallback,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { IconButton } from "./IconButton";
import { ToastContext, type ToastTone } from "./toast-context";

interface ToastItem {
  id: number;
  message: string;
  tone: ToastTone;
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);
  const showToast = useCallback((message: string, tone: ToastTone = "success") => {
    const id = Date.now() + Math.random();
    setToasts((current) => [...current, { id, message, tone }]);
    window.setTimeout(() => dismiss(id), 4000);
  }, [dismiss]);
  const value = useMemo(() => ({ showToast }), [showToast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-region" aria-live="polite" aria-atomic="true">
        {toasts.map((toast) => {
          const StatusIcon = toast.tone === "success" ? CircleCheck : CircleX;
          return (
            <div className={`toast toast--${toast.tone}`} key={toast.id} role="status">
              <StatusIcon aria-hidden="true" />
              <span>{toast.message}</span>
              <IconButton
                label="Скрыть уведомление"
                icon={X}
                size="small"
                onClick={() => dismiss(toast.id)}
              />
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}
