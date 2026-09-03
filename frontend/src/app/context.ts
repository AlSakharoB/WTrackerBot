import { useOutletContext } from "react-router-dom";

import type {
  CurrentUser,
  UIPreferences,
  UIPreferencesUpdate,
} from "../api/client";

export interface MiniAppContext {
  user: CurrentUser | null;
  initData: string;
  preferences: UIPreferences;
  isDevelopmentPreview: boolean;
  updatePreferences: (update: UIPreferencesUpdate) => Promise<void>;
  preferencesPending: boolean;
}

export function useMiniAppContext() {
  return useOutletContext<MiniAppContext>();
}
