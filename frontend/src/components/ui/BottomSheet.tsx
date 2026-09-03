import { X } from "lucide-react";
import { useEffect, useRef, type ReactNode } from "react";

import { IconButton } from "./IconButton";

interface BottomSheetProps {
  open: boolean;
  title: string;
  children: ReactNode;
  onClose: () => void;
}

export function BottomSheet({ open, title, children, onClose }: BottomSheetProps) {
  const sheetRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!open) return;
    sheetRef.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onClose, open]);

  if (!open) return null;
  return (
    <div className="sheet-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        ref={sheetRef}
        className="bottom-sheet"
        role="dialog"
        aria-modal="true"
        aria-labelledby="sheet-title"
        tabIndex={-1}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="bottom-sheet__handle" aria-hidden="true" />
        <header>
          <h2 id="sheet-title">{title}</h2>
          <IconButton label="Закрыть" icon={X} onClick={onClose} />
        </header>
        <div className="bottom-sheet__content">{children}</div>
      </section>
    </div>
  );
}
