import { Trash2 } from "lucide-react";
import { animate, motion, useMotionValue, useReducedMotion } from "motion/react";
import { useEffect, useRef, useState, type ReactNode, type PointerEvent } from "react";

const ACTION_WIDTH = 72;
const MOVEMENT_TOLERANCE = 10;
export const LONG_PRESS_MS = 450;

interface SwipeableRowProps {
  children: ReactNode;
  label: string;
  open: boolean;
  disabled?: boolean;
  onOpenChange: (open: boolean) => void;
  onDelete: () => void;
  onLongPress?: () => void;
}

export function SwipeableRow({ children, label, open, disabled = false, onOpenChange, onDelete, onLongPress }: SwipeableRowProps) {
  const ref = useRef<HTMLDivElement>(null);
  const gesture = useRef<{ id: number; x: number; y: number; start: number; horizontal: boolean } | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const suppressClick = useRef(false);
  const x = useMotionValue(0);
  const reducedMotion = useReducedMotion();
  const [swiping, setSwiping] = useState(false);
  const clearHold = () => window.clearTimeout(timer.current);

  useEffect(() => {
    const animation = animate(x, open && !disabled ? -ACTION_WIDTH : 0, { duration: reducedMotion ? 0 : 0.18 });
    return () => animation.stop();
  }, [disabled, open, reducedMotion, x]);

  useEffect(() => () => window.clearTimeout(timer.current), []);

  useEffect(() => {
    if (!open) return;
    const outside = (event: globalThis.PointerEvent) => {
      if (event.target instanceof Node && !ref.current?.contains(event.target)) onOpenChange(false);
    };
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") onOpenChange(false); };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, [onOpenChange, open]);

  const finish = (event: PointerEvent<HTMLDivElement>, cancelled = false) => {
    clearHold();
    const current = gesture.current;
    gesture.current = null;
    setSwiping(false);
    if (!current || current.id !== event.pointerId || !current.horizontal) return;
    const nextOpen = !cancelled && !disabled && x.get() < -ACTION_WIDTH / 2;
    onOpenChange(nextOpen);
    animate(x, nextOpen ? -ACTION_WIDTH : 0, { duration: reducedMotion ? 0 : 0.18 });
  };

  return (
    <div ref={ref} className={`swipe-row ${swiping ? "is-swiping" : ""}`} data-open={open}>
      <button
        type="button"
        className="swipe-row__delete"
        aria-label={`Удалить ${label}`}
        title="Удалить"
        aria-hidden={!open}
        tabIndex={open ? 0 : -1}
        disabled={!open || disabled}
        onClick={() => { onOpenChange(false); onDelete(); }}
      ><Trash2 aria-hidden="true" /></button>
      <motion.div
        className="swipe-row__content"
        style={{ x }}
        onContextMenu={(event) => event.preventDefault()}
        onClickCapture={(event) => {
          if (suppressClick.current && event.detail !== 0) {
            event.preventDefault();
            event.stopPropagation();
          } else if (open) {
            event.preventDefault();
            event.stopPropagation();
            onOpenChange(false);
          }
          suppressClick.current = false;
        }}
        onPointerDown={(event) => {
          clearHold();
          if (disabled || event.button !== 0 || !event.isPrimary || gesture.current
            || (event.target as Element).closest("[data-row-action]")) return;
          suppressClick.current = false;
          x.stop();
          gesture.current = { id: event.pointerId, x: event.clientX, y: event.clientY, start: x.get(), horizontal: false };
          if (onLongPress && !open) timer.current = window.setTimeout(() => {
            gesture.current = null;
            suppressClick.current = true;
            onLongPress();
          }, LONG_PRESS_MS);
        }}
        onPointerMove={(event) => {
          const current = gesture.current;
          if (!current || current.id !== event.pointerId) return;
          if (disabled) { clearHold(); gesture.current = null; suppressClick.current = true; return; }
          const dx = event.clientX - current.x;
          const dy = event.clientY - current.y;
          if (!current.horizontal) {
            if (Math.hypot(dx, dy) < MOVEMENT_TOLERANCE) return;
            clearHold();
            suppressClick.current = true;
            if (Math.abs(dy) >= Math.abs(dx)) { gesture.current = null; return; }
            current.horizontal = true;
            event.currentTarget.setPointerCapture?.(event.pointerId);
            setSwiping(true);
          }
          event.preventDefault();
          x.set(Math.max(-ACTION_WIDTH, Math.min(0, current.start + dx)));
        }}
        onPointerUp={(event) => finish(event)}
        onPointerCancel={(event) => finish(event, true)}
        onLostPointerCapture={(event) => { if (event.target === event.currentTarget) finish(event, true); }}
      >{children}</motion.div>
    </div>
  );
}
