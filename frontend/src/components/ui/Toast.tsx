import { CircleCheck, CircleX, X } from "lucide-react";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";

import { IconButton } from "./IconButton";
import { ToastContext, type ToastTone } from "./toast-context";

interface ToastItem {
  id: number;
  message: string;
  tone: ToastTone;
  leaving: boolean;
}

const MAX_TOASTS = 2;
const TOAST_DURATION_MS = 2000;
const TOAST_EXIT_MS = 180;

function reconcileToasts(current: ToastItem[], requested: ToastItem[]): ToastItem[] {
  const existing = current.map((toast) => ({
    ...toast,
    leaving: toast.leaving || !requested.some((item) => item.id === toast.id),
  }));
  const incoming = requested.filter((item) => !current.some((toast) => toast.id === item.id));
  return [...existing, ...incoming.slice(0, MAX_TOASTS - existing.length)];
}

function ToastMessage({ toast, onDismiss, onRemove }: {
  toast: ToastItem;
  onDismiss: (id: number) => void;
  onRemove: (id: number) => void;
}) {
  useEffect(() => {
    const timer = window.setTimeout(() => onDismiss(toast.id), TOAST_DURATION_MS);
    return () => window.clearTimeout(timer);
  }, [onDismiss, toast.id]);
  useEffect(() => {
    if (!toast.leaving) return;
    const timer = window.setTimeout(() => onRemove(toast.id), TOAST_EXIT_MS);
    return () => window.clearTimeout(timer);
  }, [onRemove, toast.id, toast.leaving]);
  const StatusIcon = toast.tone === "success" ? CircleCheck : CircleX;
  return (
    <div
      className={`toast toast--${toast.tone}${toast.leaving ? " is-leaving" : ""}`}
      role={toast.tone === "error" ? "alert" : "status"}
      aria-hidden={toast.leaving || undefined}
      onAnimationEnd={(event) => {
        if (toast.leaving && event.target === event.currentTarget) onRemove(toast.id);
      }}
    >
      <StatusIcon aria-hidden="true" />
      <span>{toast.message}</span>
      <IconButton
        label="Скрыть уведомление"
        icon={X}
        size="small"
        onClick={() => onDismiss(toast.id)}
      />
    </div>
  );
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const requested = useRef<ToastItem[]>([]);
  const nextId = useRef(0);
  const dismiss = useCallback((id: number) => {
    requested.current = requested.current.filter((toast) => toast.id !== id);
    setToasts((current) => reconcileToasts(current, requested.current));
  }, []);
  const remove = useCallback((id: number) => {
    setToasts((current) => reconcileToasts(
      current.filter((toast) => toast.id !== id), requested.current,
    ));
  }, []);
  const showToast = useCallback((message: string, tone: ToastTone = "success") => {
    const toast: ToastItem = { id: ++nextId.current, message, tone, leaving: false };
    requested.current = [...requested.current, toast].slice(-MAX_TOASTS);
    setToasts((current) => reconcileToasts(current, requested.current));
  }, []);
  const value = useMemo(() => ({ showToast }), [showToast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      {createPortal(
        <div className="toast-region" aria-relevant="additions removals">
          {toasts.map((toast) => <ToastMessage key={toast.id} toast={toast} onDismiss={dismiss} onRemove={remove} />)}
        </div>,
        document.body,
      )}
    </ToastContext.Provider>
  );
}
