import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/Badge";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { listAuditLog } from "@/lib/api/audit";
import { listCustomers } from "@/lib/api/customers";
import { getHeartbeatSummary } from "@/lib/api/heartbeats";
import { listLicenses } from "@/lib/api/licenses";
import { useSession } from "@/hooks/useSession";
import { useT } from "@/lib/i18n";

/**
 * 跨资源概览页，并发拉 4 个端点；任一失败不影响其它块渲染。
 */
export default function DashboardPage() {
  const session = useSession();
  const t = useT();
  const customers = useQuery({
    queryKey: ["dashboard", "customers"],
    queryFn: () => listCustomers({ limit: 1, status: "active" }),
  });
  const licenses = useQuery({
    queryKey: ["dashboard", "licenses"],
    queryFn: () => listLicenses({ limit: 5 }),
  });
  const heartbeats = useQuery({
    queryKey: ["dashboard", "heartbeats"],
    queryFn: () => getHeartbeatSummary(86_400, 200),
    refetchInterval: 30_000,
  });
  const audit = useQuery({
    queryKey: ["dashboard", "audit"],
    queryFn: () => listAuditLog({ limit: 8 }),
  });

  const activeCustomers = customers.data?.items.length ?? 0; // 仅占位：list 端点不返回 total，这里只表"至少 1"
  const recentLicenses = licenses.data?.items ?? [];
  const summary = heartbeats.data?.items ?? [];
  const anomalyLicenses = summary.filter((s) => s.anomaly);
  const totalHeartbeats = summary.reduce((sum, s) => sum + s.total_count, 0);
  const recentEvents = audit.data?.items ?? [];

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          {session.data
            ? t("page.dashboard.welcome", { name: session.data.username })
            : t("page.dashboard.welcome_anon")}
        </h1>
        <p className="mt-1 text-sm text-fg/60">{t("page.dashboard.overview")}</p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <StatCard
          to="/customers"
          label={t("dashboard.card.active_customers")}
          value={activeCustomers > 0 ? "≥ 1" : "0"}
          hint={customers.isLoading ? t("common.loading_inline") : t("dashboard.card.click_for_list")}
        />
        <StatCard
          to="/licenses"
          label={t("dashboard.card.recent_licenses")}
          value={String(recentLicenses.length)}
          hint={licenses.isLoading ? t("common.loading_inline") : t("dashboard.card.last_5_issued")}
        />
        <StatCard
          to="/heartbeats"
          label={t("dashboard.card.heartbeats_24h")}
          value={String(totalHeartbeats)}
          hint={heartbeats.isLoading ? t("common.loading_inline") : t("dashboard.card.across_all")}
        />
        <StatCard
          to="/heartbeats"
          label={t("dashboard.card.anomalies")}
          value={String(anomalyLicenses.length)}
          tone={anomalyLicenses.length > 0 ? "danger" : "neutral"}
          hint={
            anomalyLicenses.length > 0
              ? t("dashboard.card.anomalies_flagged")
              : heartbeats.isLoading
                ? t("common.loading_inline")
                : t("dashboard.card.all_clear")
          }
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>{t("dashboard.section.recent_licenses")}</CardTitle>
          </CardHeader>
          <CardBody className="p-0">
            {licenses.isLoading ? (
              <Empty>{t("common.loading")}</Empty>
            ) : licenses.isError ? (
              <Empty tone="error">{t("common.failed")}: {(licenses.error as Error).message}</Empty>
            ) : recentLicenses.length === 0 ? (
              <Empty>{t("dashboard.empty.no_licenses")}</Empty>
            ) : (
              <ul className="divide-y divide-border">
                {recentLicenses.map((lic) => {
                  const expired = new Date(lic.expires_at).getTime() < Date.now();
                  return (
                    <li
                      key={lic.license_id}
                      className="flex items-center justify-between gap-4 px-5 py-3 transition-soft hover:bg-muted/40"
                    >
                      <div className="min-w-0">
                        <Link
                          to={`/licenses/${lic.license_id}`}
                          className="block truncate font-mono text-xs hover:underline"
                        >
                          {lic.license_id}
                        </Link>
                        <div className="mt-0.5 truncate text-xs text-fg/60">
                          {lic.customer_id} · {lic.product_id} · {lic.algorithm}
                        </div>
                      </div>
                      <div className="flex items-center gap-2 whitespace-nowrap text-xs text-fg/70">
                        <Badge tone={expired ? "warning" : "success"}>
                          {expired ? "expired" : "active"}
                        </Badge>
                        <span>{new Date(lic.expires_at).toLocaleDateString()}</span>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{t("dashboard.section.recent_activity")}</CardTitle>
          </CardHeader>
          <CardBody className="p-0">
            {audit.isLoading ? (
              <Empty>{t("common.loading")}</Empty>
            ) : audit.isError ? (
              <Empty tone="error">{t("common.failed")}: {(audit.error as Error).message}</Empty>
            ) : recentEvents.length === 0 ? (
              <Empty>{t("dashboard.empty.no_licenses")}</Empty>
            ) : (
              <ul className="divide-y divide-border">
                {recentEvents.map((event) => {
                  const tone: React.ComponentProps<typeof Badge>["tone"] = event.action.includes(
                    "failure",
                  )
                    ? "danger"
                    : event.action.includes("revoked") || event.action.includes("archived")
                    ? "warning"
                    : "neutral";
                  return (
                    <li
                      key={event.id}
                      className="flex items-center justify-between gap-3 px-5 py-3 text-sm transition-soft hover:bg-muted/40"
                    >
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <Badge tone={tone}>{event.action}</Badge>
                          <span className="truncate font-mono text-xs text-fg/60">
                            {event.target_type}:{event.target_id.slice(0, 12)}
                          </span>
                        </div>
                        <div className="mt-0.5 truncate text-xs text-fg/50">
                          {event.actor_type}:{event.actor_id}
                          {event.client_ip ? ` · ${event.client_ip}` : ""}
                        </div>
                      </div>
                      <div className="whitespace-nowrap text-xs text-fg/60">
                        {new Date(event.occurred_at).toLocaleTimeString()}
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
            <div className="border-t border-border px-5 py-3 text-right text-xs">
              <Link className="text-primary hover:underline" to="/audit">
                {t("dashboard.link.audit")}
              </Link>
            </div>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}

function StatCard({
  to,
  label,
  value,
  hint,
  tone = "neutral",
}: {
  to: string;
  label: string;
  value: string;
  hint?: string;
  tone?: "neutral" | "danger";
}) {
  return (
    <Link
      to={to}
      className="block rounded-2xl border border-border bg-bg p-5 shadow-sm transition-soft hover:bg-muted/40 hover:shadow-md"
    >
      <div className="text-xs uppercase tracking-wider text-fg/50">{label}</div>
      <div
        className={`mt-1 text-3xl font-semibold ${
          tone === "danger" ? "text-red-600" : "text-fg"
        }`}
      >
        {value}
      </div>
      {hint && <div className="mt-1 text-xs text-fg/60">{hint}</div>}
    </Link>
  );
}

function Empty({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: "neutral" | "error";
}) {
  return (
    <div
      className={`px-5 py-8 text-center text-sm ${
        tone === "error" ? "text-red-600" : "text-fg/50"
      }`}
    >
      {children}
    </div>
  );
}
