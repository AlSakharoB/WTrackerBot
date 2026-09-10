import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";

import {
  fetchCurrentUser,
  fetchUIPreferences,
  updateUIPreferences,
  type DefaultSection,
  type UIPreferences,
  type UIPreferencesUpdate,
} from "../api/client";
import { AppShell } from "../components/layout/AppShell";
import { ErrorState, Skeleton, ToastProvider } from "../components/ui";
import { FoodPage } from "../pages/FoodPage";
import { ProfilePage } from "../pages/ProfilePage";
import { PrivacyPolicyPage } from "../pages/PrivacyPolicyPage";
import { RationPage } from "../pages/RationPage";
import { WeightPage } from "../pages/WeightPage";
import type { TelegramAdapter } from "../telegram/adapter";
import { useTelegramEnvironment } from "../telegram/hooks";
import type { MiniAppContext } from "./context";

const DEFAULT_PREFERENCES: UIPreferences = {
  theme_mode: "system",
  default_section: "ration",
  default_weight_unit: "kg",
  compact_lists: false,
  updated_at: "",
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
  const stored = localStorage.getItem("miniapp:last-section") as DefaultSection | null;
  const section = stored && VALID_SECTIONS.has(stored) ? stored : defaultSection;
  return <Navigate replace to={`/${section}`} />;
}

export function App({ telegram }: AppProps) {
  const queryClient = useQueryClient();
  const location = useLocation();
  const [previewPreferences, setPreviewPreferences] = useState(DEFAULT_PREFERENCES);
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
  const preferencesMutation = useMutation({
    mutationFn: (update: UIPreferencesUpdate) =>
      updateUIPreferences(telegram.initData, update),
    onSuccess: (preferences) => {
      queryClient.setQueryData(["ui-preferences"], preferences);
    },
  });

  const preferences = hasAuthorization
    ? (preferencesQuery.data ?? DEFAULT_PREFERENCES)
    : previewPreferences;
  useTelegramEnvironment(telegram, preferences.theme_mode);

  if (location.pathname === "/privacy-policy") {
    return <PrivacyPolicyPage />;
  }

  if (!allowApplication) {
    return (
      <main className="status-screen">
        <section aria-labelledby="auth-title">
          <p className="eyebrow">WTrackerBot Mini App</p>
          <h1 id="auth-title">Откройте приложение из Telegram</h1>
          <p>Авторизационные данные Telegram не получены.</p>
        </section>
      </main>
    );
  }

  if (hasAuthorization && (userQuery.isPending || preferencesQuery.isPending)) {
    return <main className="status-screen"><Skeleton lines={4} /></main>;
  }

  const failedQuery = userQuery.error ?? preferencesQuery.error;
  if (hasAuthorization && failedQuery) {
    return (
      <main className="status-screen">
        <ErrorState
          title="Не удалось открыть приложение"
          message={failedQuery.message}
          onRetry={() => {
            void userQuery.refetch();
            void preferencesQuery.refetch();
          }}
        />
      </main>
    );
  }

  const updatePreferences = async (update: UIPreferencesUpdate) => {
    if (hasAuthorization) {
      await preferencesMutation.mutateAsync(update);
      return;
    }
    setPreviewPreferences((current) => ({ ...current, ...update }));
  };
  const context: MiniAppContext = {
    user: userQuery.data ?? null,
    initData: telegram.initData,
    preferences,
    isDevelopmentPreview: telegram.isDevelopmentPreview,
    updatePreferences,
    preferencesPending: preferencesMutation.isPending,
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
          <Route path="/weight" element={<WeightPage />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route
            path="*"
            element={
              <div className="page">
                <ErrorState
                  title="Раздел не найден"
                  message="Вернитесь в один из основных разделов."
                />
              </div>
            }
          />
        </Route>
      </Routes>
    </ToastProvider>
  );
}
