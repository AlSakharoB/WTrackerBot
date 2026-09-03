import type { LucideIcon } from "lucide-react";
import type { ButtonHTMLAttributes } from "react";

interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  label: string;
  icon: LucideIcon;
  size?: "default" | "small";
}

export function IconButton({
  label,
  icon: Icon,
  size = "default",
  className = "",
  ...props
}: IconButtonProps) {
  return (
    <button
      type="button"
      className={`icon-button icon-button--${size} ${className}`.trim()}
      aria-label={label}
      title={label}
      {...props}
    >
      <Icon aria-hidden="true" size={size === "small" ? 18 : 20} />
    </button>
  );
}
