import { createBrowserRouter, Navigate } from "react-router-dom";

import { AppShell } from "@/components/AppShell";
import { AuthGuard } from "@/components/AuthGuard";

/**
 * 路由 — feature 全部走 lazy split，避免登录页拖入 customers 的代码。
 * 已挂载：login / customers (list, detail)。
 * 后续 feature 在 AuthGuard 子树里追加。
 */
export const router = createBrowserRouter([
  { path: "/login", lazy: () => import("@/features/auth/login") },
  {
    element: <AuthGuard />,
    children: [
      {
        element: <AppShell />,
        children: [
          { index: true, element: <Navigate to="/dashboard" replace /> },
          { path: "/dashboard", lazy: () => import("@/features/dashboard") },
          { path: "/customers", lazy: () => import("@/features/customers/list") },
          { path: "/customers/:id", lazy: () => import("@/features/customers/detail") },
          // 静态 /licenses/issue 与 /licenses/verify 必须先于动态 /licenses/:id 注册
          { path: "/licenses", lazy: () => import("@/features/licenses/list") },
          { path: "/licenses/issue", lazy: () => import("@/features/licenses/issue") },
          { path: "/licenses/verify", lazy: () => import("@/features/licenses/verify") },
          { path: "/licenses/:id", lazy: () => import("@/features/licenses/detail") },
          { path: "/api-keys", lazy: () => import("@/features/api_keys/list") },
          { path: "/keys", lazy: () => import("@/features/keys/list") },
          { path: "/products", lazy: () => import("@/features/products/list") },
          { path: "/products/:id", lazy: () => import("@/features/products/detail") },
          { path: "/heartbeats", lazy: () => import("@/features/heartbeats/list") },
          { path: "/heartbeats/:id", lazy: () => import("@/features/heartbeats/detail") },
          { path: "/audit", lazy: () => import("@/features/audit/list") },
          { path: "/admin/users", lazy: () => import("@/features/admin_users/list") },
        ],
      },
    ],
  },
  { path: "*", element: <div className="p-8">404 Not Found</div> },
]);
