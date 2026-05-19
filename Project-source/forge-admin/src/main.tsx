import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "react-router-dom";

import { ToastProvider } from "@/components/ui/Toast";
import { router } from "@/routes";
import { resolveConfig } from "@/lib/api/client";
import { I18nProvider } from "@/lib/i18n";
import { applyBrandPrimary, applyTheme, loadStoredTheme } from "@/lib/theme/theme";
import "@/styles.css";

// 启动时同步主题 + 客户品牌色，避免 FOUC
applyTheme(loadStoredTheme());
applyBrandPrimary(resolveConfig().brandPrimaryHsl);

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    },
  },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <ToastProvider>
          <RouterProvider router={router} />
        </ToastProvider>
      </I18nProvider>
    </QueryClientProvider>
  </React.StrictMode>,
);
