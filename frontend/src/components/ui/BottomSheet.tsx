import { X } from "lucide-react";
import { AnimatePresence } from "motion/react";
import { useId, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { IconButton } from "./IconButton";
import { ModalSurface } from "./ModalSurface";

interface BottomSheetProps {
  open: boolean;
  title: string;
  children: ReactNode;
  onClose: () => void;
}

export function BottomSheet({ open, title, children, onClose }: BottomSheetProps) {
  const titleId = useId();
  return createPortal(
    <AnimatePresence propagate={open}>
      {open && <ModalSurface key="sheet" kind="sheet" titleId={titleId} onClose={onClose}>
        <div className="bottom-sheet__handle" aria-hidden="true" />
        <header>
          <h2 id={titleId}>{title}</h2>
          <IconButton label="Закрыть" icon={X} onClick={onClose} />
        </header>
        <div className="bottom-sheet__content">{children}</div>
      </ModalSurface>}
    </AnimatePresence>,
    document.body,
  );
}
