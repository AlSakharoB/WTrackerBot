import { motion, useIsPresent, useReducedMotion } from "motion/react";
import { useRef, type ReactNode, type RefObject } from "react";

import { useModalLayer } from "./useModalLayer";

interface ModalSurfaceProps {
  kind: "sheet" | "dialog";
  titleId: string;
  descriptionId?: string;
  initialFocusRef?: RefObject<HTMLElement | null>;
  onClose: () => void;
  children: ReactNode;
}

export function ModalSurface({ kind, titleId, descriptionId, initialFocusRef, onClose, children }: ModalSurfaceProps) {
  const containerRef = useRef<HTMLElement>(null);
  const present = useIsPresent();
  const reducedMotion = useReducedMotion();
  const { backdropHandlers } = useModalLayer({
    open: true,
    containerRef,
    initialFocusRef,
    onClose: () => { if (present) onClose(); },
  });
  const sheet = kind === "sheet";

  return (
    <motion.div
      className={sheet ? "sheet-backdrop" : "dialog-backdrop"}
      data-state={present ? "open" : "closing"}
      role="presentation"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: reducedMotion ? 0 : 0.24 }}
      {...backdropHandlers}
    >
      <motion.section
        ref={containerRef}
        className={sheet ? "bottom-sheet" : "confirm-dialog"}
        role={sheet ? "dialog" : "alertdialog"}
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        aria-hidden={!present || undefined}
        inert={!present}
        tabIndex={-1}
        initial={reducedMotion ? false : { y: sheet ? "100%" : 16, opacity: sheet ? 1 : 0 }}
        animate={{ y: 0, opacity: 1 }}
        exit={{ y: reducedMotion ? 0 : sheet ? "100%" : 16, opacity: sheet ? 1 : 0 }}
        transition={{ duration: reducedMotion ? 0 : 0.28, ease: [0.22, 1, 0.36, 1] }}
      >
        {children}
      </motion.section>
    </motion.div>
  );
}
