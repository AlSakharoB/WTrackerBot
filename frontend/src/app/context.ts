import { useOutletContext } from "react-router-dom";

import type {
  CurrentUser,
  Profile,
  ProfileSettingsUpdate,
  UIPreferences,
  UIPreferencesUpdate,
} from "../api/client";

export interface MiniAppContext {
  user: CurrentUser | null;
  profile: Profile;
  initData: string;
  preferences: UIPreferences;
  isDevelopmentPreview: boolean;
  updatePreferences: (update: UIPreferencesUpdate) => Promise<void>;
  updateProfile: (update: ProfileSettingsUpdate) => Promise<void>;
  preferencesPending: boolean;
  profilePending: boolean;
  closeMiniApp: () => void;
  hapticFeedback?: (kind: "selection" | "success") => void;
}

export function useMiniAppContext() {
  return useOutletContext<MiniAppContext>();
}
