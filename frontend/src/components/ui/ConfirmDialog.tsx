import { AnimatePresence } from "motion/react";
import { useId, useRef } from "react";
import { createPortal } from "react-dom";

import { ModalSurface } from "./ModalSurface";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description: string;
  confirmLabel?: string;
  destructive?: boolean;
  confirmDisabled?: boolean;
  onConfirm: () => void;
  onClose: () => void;
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "Подтвердить",
  destructive = false,
  confirmDisabled = false,
  onConfirm,
  onClose,
}: ConfirmDialogProps) {
  const cancelRef = useRef<HTMLButtonElement>(null);
  const titleId = useId();
  const descriptionId = useId();
  return createPortal(
    <AnimatePresence propagate={open}>
      {open && <ModalSurface key="dialog" kind="dialog" titleId={titleId} descriptionId={descriptionId} initialFocusRef={cancelRef} onClose={onClose}>
        <h2 id={titleId}>{title}</h2>
        <p id={descriptionId}>{description}</p>
        <div className="dialog-actions">
          <button ref={cancelRef} type="button" className="button-secondary" onClick={onClose}>
            Отмена
          </button>
          <button
            type="button"
            className={destructive ? "button-danger" : "button-primary"}
            disabled={confirmDisabled}
            onClick={onConfirm}
          >
            {confirmLabel}
          </button>
        </div>
      </ModalSurface>}
    </AnimatePresence>,
    document.body,
  );
}
