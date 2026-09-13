import { useEffect, useRef, type RefObject } from "react";

import {
  hasOpenModalLayer,
  isTopModalLayer,
  registerModalLayer,
} from "./modal-stack";

const FOCUSABLE_SELECTOR = [
  "button:not([disabled])",
  "a[href]",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

function focusableElements(container: HTMLElement): HTMLElement[] {
  return [...container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)].filter(
    (element) => {
      const style = getComputedStyle(element);
      return !element.hidden && style.display !== "none" && style.visibility !== "hidden";
    },
  );
}

interface UseModalLayerOptions {
  open: boolean;
  containerRef: RefObject<HTMLElement | null>;
  initialFocusRef?: RefObject<HTMLElement | null>;
  onClose: () => void;
}

export function useModalLayer({
  open,
  containerRef,
  initialFocusRef,
  onClose,
}: UseModalLayerOptions) {
  const idRef = useRef(Symbol("modal-layer"));
  const onCloseRef = useRef(onClose);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (!open) return;

    const id = idRef.current;
    const trigger = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    const unregister = registerModalLayer({ id, close: () => onCloseRef.current() });
    const appRoot = document.getElementById("root");
    const initialFocus = initialFocusRef?.current ?? containerRef.current;
    initialFocus?.focus({ preventScroll: true });
    if (appRoot) appRoot.inert = true;
    document.body.dataset.overlayOpen = "true";

    const handleKeyDown = (event: KeyboardEvent) => {
      if (!isTopModalLayer(id)) return;
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab" || !containerRef.current) return;

      const focusable = focusableElements(containerRef.current);
      if (focusable.length === 0) {
        event.preventDefault();
        containerRef.current.focus({ preventScroll: true });
        return;
      }
      const first = focusable[0];
      const last = focusable.at(-1)!;
      const active = document.activeElement;
      if (event.shiftKey && (active === first || !containerRef.current.contains(active))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (active === last || !containerRef.current.contains(active))) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      unregister();
      if (!hasOpenModalLayer()) {
        document.body.removeAttribute("data-overlay-open");
        if (appRoot) appRoot.inert = false;
      }
      if (trigger?.isConnected) trigger.focus({ preventScroll: true });
    };
  }, [containerRef, initialFocusRef, open]);

  return {
    isTopLayer: () => isTopModalLayer(idRef.current),
  };
}
