import { Apple, ChartNoAxesColumnIncreasing, UserRound, Utensils } from "lucide-react";
import { NavLink } from "react-router-dom";

const ITEMS = [
  { to: "/ration", label: "Рацион", icon: Utensils },
  { to: "/food", label: "Еда", icon: Apple },
  { to: "/weight", label: "Вес", icon: ChartNoAxesColumnIncreasing },
  { to: "/profile", label: "Профиль", icon: UserRound },
] as const;

export function BottomNavigation() {
  return (
    <nav className="bottom-navigation" aria-label="Основные разделы">
      {ITEMS.map(({ to, label, icon: Icon }) => (
        <NavLink
          key={to}
          to={to}
          className={({ isActive }) => isActive ? "is-active" : undefined}
        >
          <span className="bottom-navigation__icon"><Icon aria-hidden="true" /></span>
          <span>{label}</span>
        </NavLink>
      ))}
    </nav>
  );
}
