import { CircleCheck, CircleX, X } from "lucide-react";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
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
  const timers = useRef(new Map<number, number>());
  const dismiss = useCallback((id: number) => {
    const timer = timers.current.get(id);
    if (timer !== undefined) window.clearTimeout(timer);
    timers.current.delete(id);
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);
  const showToast = useCallback((message: string, tone: ToastTone = "success") => {
    const id = Date.now() + Math.random();
    setToasts((current) => [...current, { id, message, tone }]);
    timers.current.set(id, window.setTimeout(() => dismiss(id), 4000));
  }, [dismiss]);
  useEffect(() => () => {
    for (const timer of timers.current.values()) window.clearTimeout(timer);
    timers.current.clear();
  }, []);
  const value = useMemo(() => ({ showToast }), [showToast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-region" aria-relevant="additions removals">
        {toasts.map((toast) => {
          const StatusIcon = toast.tone === "success" ? CircleCheck : CircleX;
          return (
            <div
              className={`toast toast--${toast.tone}`}
              key={toast.id}
              role={toast.tone === "error" ? "alert" : "status"}
            >
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
