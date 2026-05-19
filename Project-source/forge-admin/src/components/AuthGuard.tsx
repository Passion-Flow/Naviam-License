import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useSession } from "@/hooks/useSession";

/**
 * 路由级鉴权闸门 —— `useSession` 拉 /auth/me，401 → 跳 /login。
 * 已登录 → 渲染 <Outlet/>（下游布局负责把 user 传下去）。
 */
export function AuthGuard() {
  const session = useSession();
  const location = useLocation();

  if (session.isLoading) {
    return <div className="grid min-h-screen place-items-center text-sm text-fg/60">Loading…</div>;
  }
  if (!session.data) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }
  return <Outlet />;
}
