import { X } from "lucide-react";
import { useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";

import { IconButton } from "./IconButton";
import { useModalLayer } from "./useModalLayer";

interface BottomSheetProps {
  open: boolean;
  title: string;
  children: ReactNode;
  onClose: () => void;
}

export function BottomSheet({ open, title, children, onClose }: BottomSheetProps) {
  const sheetRef = useRef<HTMLElement>(null);
  const titleId = useId();
  const { isTopLayer } = useModalLayer({
    open,
    containerRef: sheetRef,
    onClose,
  });

  if (!open) return null;
  return createPortal(
    <div
      className="sheet-backdrop"
      role="presentation"
      onPointerDown={(event) => {
        if (event.target === event.currentTarget && isTopLayer()) onClose();
      }}
    >
      <section
        ref={sheetRef}
        className="bottom-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
      >
        <div className="bottom-sheet__handle" aria-hidden="true" />
        <header>
          <h2 id={titleId}>{title}</h2>
          <IconButton label="Закрыть" icon={X} onClick={onClose} />
        </header>
        <div className="bottom-sheet__content">{children}</div>
      </section>
    </div>,
    document.body,
  );
}
