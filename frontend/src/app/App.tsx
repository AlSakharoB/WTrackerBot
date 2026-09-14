import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { lazy, Suspense, useState } from "react";
import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { LockKeyhole, RefreshCw, RouteOff } from "lucide-react";

import {
  APIError,
  fetchCurrentUser,
  fetchProfile,
  fetchUIPreferences,
  updateProfileSettings,
  updateUIPreferences,
  type DefaultSection,
  type Profile,
  type ProfileSettingsUpdate,
  type UIPreferences,
  type UIPreferencesUpdate,
} from "../api/client";
import { AppShell } from "../components/layout/AppShell";
import { ProductState, Skeleton, ToastProvider } from "../components/ui";
import { FoodPage } from "../pages/FoodPage";
import { ProfilePage } from "../pages/ProfilePage";
import { PrivacyPolicyPage } from "../pages/PrivacyPolicyPage";
import { RationPage } from "../pages/RationPage";
import { SharePreviewPage } from "../pages/SharePreviewPage";
import type { TelegramAdapter } from "../telegram/adapter";
import { useTelegramEnvironment } from "../telegram/hooks";
import type { MiniAppContext } from "./context";

const WeightPage = lazy(() =>
  import("../pages/WeightPage").then((module) => ({ default: module.WeightPage })),
);

const DEFAULT_PREFERENCES: UIPreferences = {
  theme_mode: "system",
  default_section: "ration",
  default_weight_unit: "kg",
  compact_lists: false,
  updated_at: "",
};

const PREVIEW_PROFILE: Profile = {
  id: "preview",
  telegram_id: "preview",
  username: "preview",
  first_name: "Алексей",
  last_name: null,
  language_code: "ru",
  timezone: "Europe/Moscow",
  app_version: "dev",
  photo_url: null,
  number_format: "automatic",
  after_food_add_action: "open_today",
  confirm_deletions: true,
  reminders_enabled: false,
};

const VALID_SECTIONS = new Set<DefaultSection>([
  "ration",
  "food",
  "weight",
  "profile",
]);

interface AppProps {
  telegram: TelegramAdapter;
}

function InitialRedirect({ defaultSection }: { defaultSection: DefaultSection }) {
  const section = VALID_SECTIONS.has(defaultSection) ? defaultSection : "ration";
  return <Navigate replace to={`/${section}`} />;
}

export function App({ telegram }: AppProps) {
  const queryClient = useQueryClient();
  const location = useLocation();
  const [previewPreferences, setPreviewPreferences] = useState(DEFAULT_PREFERENCES);
  const [previewProfile, setPreviewProfile] = useState(PREVIEW_PROFILE);
  const hasAuthorization = telegram.initData.length > 0;
  const allowApplication = hasAuthorization || telegram.isDevelopmentPreview;

  const userQuery = useQuery({
    queryKey: ["current-user"],
    queryFn: () => fetchCurrentUser(telegram.initData),
    enabled: hasAuthorization,
    retry: false,
  });
  const preferencesQuery = useQuery({
    queryKey: ["ui-preferences"],
    queryFn: () => fetchUIPreferences(telegram.initData),
    enabled: hasAuthorization,
    retry: false,
  });
  const profileQuery = useQuery({
    queryKey: ["profile"],
    queryFn: () => fetchProfile(telegram.initData),
    enabled: hasAuthorization,
    retry: false,
  });
  const preferencesMutation = useMutation({
    mutationFn: (update: UIPreferencesUpdate) =>
      updateUIPreferences(telegram.initData, update),
    onSuccess: (preferences) => {
      queryClient.setQueryData(["ui-preferences"], preferences);
    },
  });
  const profileMutation = useMutation({
    mutationFn: (update: ProfileSettingsUpdate) =>
      updateProfileSettings(telegram.initData, update),
    onSuccess: (profile) => {
      queryClient.setQueryData(["profile"], profile);
    },
  });

  const preferences = hasAuthorization
    ? (preferencesQuery.data ?? DEFAULT_PREFERENCES)
    : previewPreferences;
  const profile = hasAuthorization
    ? (profileQuery.data ?? { ...PREVIEW_PROFILE, ...(userQuery.data ?? {}) })
    : previewProfile;
  useTelegramEnvironment(telegram, preferences.theme_mode);

  if (location.pathname === "/privacy-policy") {
    return <PrivacyPolicyPage />;
  }

  if (!allowApplication) {
    return (
      <ProductState
        icon={LockKeyhole}
        eyebrow="WTrackerBot Mini App"
        title="Откройте приложение из Telegram"
        message="Авторизационные данные Telegram не получены. Вернитесь в диалог с ботом и откройте Mini App из меню."
      />
    );
  }

  if (hasAuthorization && (userQuery.isPending || preferencesQuery.isPending || profileQuery.isPending)) {
    return <ProductState busy title="Запускаем WTracker" message="Загружаем профиль и настройки приложения." />;
  }

  const failedQuery = userQuery.error ?? preferencesQuery.error ?? profileQuery.error;
  if (hasAuthorization && failedQuery) {
    const offline = !navigator.onLine;
    const failureMessage = failedQuery instanceof APIError && failedQuery.correlationId
      ? `${failedQuery.message} (Correlation ID: ${failedQuery.correlationId})`
      : failedQuery.message;
    return (
      <ProductState
        icon={RefreshCw}
        tone="error"
        title={offline ? "Нет подключения" : "Не удалось открыть приложение"}
        message={offline ? "Проверьте интернет-соединение и повторите загрузку." : failureMessage}
        action={<button type="button" className="button-primary" onClick={() => { void userQuery.refetch(); void preferencesQuery.refetch(); void profileQuery.refetch(); }}>Повторить</button>}
      />
    );
  }

  const updatePreferences = async (update: UIPreferencesUpdate) => {
    if (hasAuthorization) {
      await preferencesMutation.mutateAsync(update);
      return;
    }
    setPreviewPreferences((current) => ({ ...current, ...update }));
  };
  const updateProfile = async (update: ProfileSettingsUpdate) => {
    if (hasAuthorization) {
      await profileMutation.mutateAsync(update);
      if (update.timezone) {
        await queryClient.invalidateQueries({ queryKey: ["current-user"] });
      }
      return;
    }
    setPreviewProfile((current) => ({ ...current, ...update }));
  };
  const context: MiniAppContext = {
    user: userQuery.data ?? null,
    profile,
    initData: telegram.initData,
    preferences,
    isDevelopmentPreview: telegram.isDevelopmentPreview,
    updatePreferences,
    updateProfile,
    preferencesPending: preferencesMutation.isPending,
    profilePending: profileMutation.isPending,
    closeMiniApp: () => telegram.close?.(),
  };

  return (
    <ToastProvider>
      <Routes>
        <Route
          path="/"
          element={<InitialRedirect defaultSection={preferences.default_section} />}
        />
        <Route element={<AppShell telegram={telegram} context={context} />}>
          <Route path="/ration" element={<RationPage />} />
          <Route path="/ration/add" element={<RationPage />} />
          <Route path="/food" element={<FoodPage />} />
          <Route path="/food/new" element={<FoodPage />} />
          <Route path="/food/share/:token" element={<SharePreviewPage />} />
          <Route
            path="/weight"
            element={<Suspense fallback={<div className="page"><Skeleton lines={7} /></div>}><WeightPage /></Suspense>}
          />
          <Route path="/profile" element={<ProfilePage />} />
        <Route
          path="*"
          element={
              <div className="page page--system-state">
                <ProductState
                  contained
                  icon={RouteOff}
                  title="Раздел не найден"
                  message="Адрес мог измениться. Вернитесь к рациону или выберите раздел в нижнем меню."
                  action={<Link className="button-primary" to={`/${preferences.default_section}`}>Вернуться в приложение</Link>}
                />
              </div>
            }
          />
        </Route>
      </Routes>
    </ToastProvider>
  );
}
