import * as React from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { ChangePasswordDialog } from "@/components/ChangePasswordDialog";
import { LanguageToggle } from "@/components/LanguageToggle";
import { SessionsDialog } from "@/components/SessionsDialog";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Button } from "@/components/ui/Button";
import { useToast } from "@/components/ui/Toast";
import { useLogout, useSession } from "@/hooks/useSession";
import { cn } from "@/lib/cn";
import { useT } from "@/lib/i18n";

interface NavItem {
  to: string;
  i18nKey: string;
}

const NAV: NavItem[] = [
  { to: "/dashboard", i18nKey: "nav.dashboard" },
  { to: "/customers", i18nKey: "nav.customers" },
  { to: "/products", i18nKey: "nav.products" },
  { to: "/licenses", i18nKey: "nav.licenses" },
  { to: "/licenses/verify", i18nKey: "nav.licenses.verify" },
  { to: "/api-keys", i18nKey: "nav.api_keys" },
  { to: "/keys", i18nKey: "nav.keys" },
  { to: "/heartbeats", i18nKey: "nav.heartbeats" },
  { to: "/audit", i18nKey: "nav.audit" },
  { to: "/admin/users", i18nKey: "nav.admin_users" },
];

/**
 * 主壳：侧栏 + 顶栏 + 内容区。所有受保护页面共用。
 */
export function AppShell() {
  const session = useSession();
  const logout = useLogout();
  const navigate = useNavigate();
  const toast = useToast();
  const t = useT();
  const [pwOpen, setPwOpen] = React.useState(false);
  const [sessionsOpen, setSessionsOpen] = React.useState(false);

  const handleLogout = React.useCallback(() => {
    logout.mutate(undefined, {
      onSuccess: () => navigate("/login", { replace: true }),
      onError: () => toast.show(t("common.logout_failed"), "error"),
    });
  }, [logout, navigate, toast]);

  return (
    <div className="flex min-h-screen bg-muted/30 text-fg">
      <aside className="hidden w-60 shrink-0 border-r border-border bg-bg md:flex md:flex-col">
        <div className="px-5 py-5">
          <div className="text-xs uppercase tracking-widest text-primary">{t("app.title")}</div>
          <div className="mt-1 text-sm font-semibold tracking-tight">{t("app.subtitle")}</div>
        </div>
        <nav className="flex-1 space-y-0.5 px-3">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                cn(
                  "block rounded-lg px-3 py-2 text-sm transition-soft",
                  isActive ? "bg-primary/10 font-medium text-primary" : "text-fg/70 hover:bg-muted",
                )
              }
            >
              {t(item.i18nKey)}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-border px-5 py-4 text-xs text-fg/60">
          {t("header.signed_in_as")}{" "}
          <span className="font-medium text-fg">{session.data?.username ?? "…"}</span>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 items-center justify-end gap-3 border-b border-border bg-bg px-6">
          <LanguageToggle />
          <ThemeToggle />
          <Button variant="ghost" size="sm" onClick={() => setSessionsOpen(true)}>
            {t("header.sessions")}
          </Button>
          <Button variant="ghost" size="sm" onClick={() => setPwOpen(true)}>
            {t("header.change_password")}
          </Button>
          <Button variant="secondary" size="sm" onClick={handleLogout} disabled={logout.isPending}>
            {logout.isPending ? t("header.signing_out") : t("header.sign_out")}
          </Button>
        </header>
        {session.data?.is_default_password && (
          <div
            role="alert"
            className="flex flex-wrap items-center justify-between gap-3 border-b border-amber-300 bg-amber-50 px-6 py-3 text-sm text-amber-900 dark:border-amber-700/60 dark:bg-amber-950/40 dark:text-amber-200"
          >
            <div>
              <span className="font-semibold">{t("banner.default_password.title")}.</span>{" "}
              {t("banner.default_password.body")}
            </div>
            <Button size="sm" onClick={() => setPwOpen(true)}>
              {t("banner.default_password.cta")}
            </Button>
          </div>
        )}
        <ChangePasswordDialog open={pwOpen} onOpenChange={setPwOpen} />
        <SessionsDialog open={sessionsOpen} onOpenChange={setSessionsOpen} />
        <main className="flex-1 px-6 py-6 lg:px-10 lg:py-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
