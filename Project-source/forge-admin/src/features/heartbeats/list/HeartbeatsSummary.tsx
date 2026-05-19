import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/Badge";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { Label } from "@/components/ui/Label";
import { Select } from "@/components/ui/Select";
import { getHeartbeatSummary } from "@/lib/api/heartbeats";
import { useT } from "@/lib/i18n";
import type { HeartbeatSummaryItem } from "@/types/api";

const WINDOW_ITEMS = [
  { value: "3600", label: "Last 1 hour" },
  { value: "86400", label: "Last 24 hours" },
  { value: "604800", label: "Last 7 days" },
  { value: "2592000", label: "Last 30 days" },
];

export default function HeartbeatsSummaryPage() {
  const t = useT();
  const [windowSeconds, setWindowSeconds] = React.useState("86400");

  const query = useQuery({
    queryKey: ["heartbeats", "summary", windowSeconds],
    queryFn: () => getHeartbeatSummary(Number(windowSeconds), 200),
    placeholderData: (prev) => prev,
    refetchInterval: 30_000, // 监控面板：30s 轮询
  });

  const anomalyCount = query.data?.items.filter((i) => i.anomaly).length ?? 0;
  const totalLicenses = query.data?.items.length ?? 0;
  const totalHeartbeats = query.data?.items.reduce((sum, i) => sum + i.total_count, 0) ?? 0;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{t("page.heartbeats.title")}</h1>
          <p className="mt-1 text-sm text-fg/60">{t("page.heartbeats.subtitle")}</p>
        </div>
        <div className="w-48 space-y-1.5">
          <Label htmlFor="window">{t("heartbeats.window")}</Label>
          <Select
            id="window"
            value={windowSeconds}
            onValueChange={setWindowSeconds}
            items={WINDOW_ITEMS}
          />
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard label={t("heartbeats.stat.active_licenses")} value={String(totalLicenses)} />
        <StatCard label={t("heartbeats.stat.received")} value={String(totalHeartbeats)} />
        <StatCard
          label={t("heartbeats.stat.anomalies")}
          value={String(anomalyCount)}
          tone={anomalyCount > 0 ? "danger" : "neutral"}
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{t("heartbeats.section.per_license")}</CardTitle>
        </CardHeader>
        <CardBody className="p-0">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-border text-sm">
              <thead className="text-left text-xs uppercase tracking-wider text-fg/60">
                <tr>
                  <Th>{t("heartbeats.col.license_id")}</Th>
                  <Th>{t("heartbeats.col.total_beats")}</Th>
                  <Th>{t("heartbeats.col.distinct_fps")}</Th>
                  <Th>{t("heartbeats.col.last_seen")}</Th>
                  <Th>{t("heartbeats.col.last_fp")}</Th>
                  <Th>{t("heartbeats.col.status")}</Th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {query.isLoading && (
                  <tr>
                    <td colSpan={6} className="px-5 py-8 text-center text-fg/50">
                      {t("common.loading")}
                    </td>
                  </tr>
                )}
                {query.isError && (
                  <tr>
                    <td colSpan={6} className="px-5 py-8 text-center text-red-600">
                      {t("detail.toast.load_failed")}: {(query.error as Error).message}
                    </td>
                  </tr>
                )}
                {query.data?.items.length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-5 py-8 text-center text-fg/50">
                      {t("heartbeats.empty.window")}
                    </td>
                  </tr>
                )}
                {query.data?.items.map((item) => <Row key={item.license_id} item={item} />)}
              </tbody>
            </table>
          </div>
        </CardBody>
      </Card>
    </div>
  );
}

function Th({ children }: { children: React.ReactNode }) {
  return <th className="whitespace-nowrap px-5 py-3 font-medium">{children}</th>;
}

function StatCard({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: string;
  tone?: "neutral" | "danger";
}) {
  return (
    <Card>
      <CardBody>
        <div className="text-xs uppercase tracking-wider text-fg/50">{label}</div>
        <div
          className={`mt-1 text-3xl font-semibold ${
            tone === "danger" ? "text-red-600" : "text-fg"
          }`}
        >
          {value}
        </div>
      </CardBody>
    </Card>
  );
}

function Row({ item }: { item: HeartbeatSummaryItem }) {
  return (
    <tr className="transition-soft hover:bg-muted/40">
      <td className="whitespace-nowrap px-5 py-3 font-mono text-xs">
        <Link to={`/heartbeats/${item.license_id}`} className="hover:underline">
          {item.license_id.slice(0, 10)}…
        </Link>
      </td>
      <td className="whitespace-nowrap px-5 py-3 text-fg/80">{item.total_count}</td>
      <td className="whitespace-nowrap px-5 py-3 text-fg/80">{item.distinct_fingerprint_count}</td>
      <td className="whitespace-nowrap px-5 py-3 text-fg/70">
        {new Date(item.last_seen_at).toLocaleString()}
      </td>
      <td className="whitespace-nowrap px-5 py-3 font-mono text-xs text-fg/60">
        {item.last_fingerprint.slice(0, 12)}…
      </td>
      <td className="whitespace-nowrap px-5 py-3">
        {item.anomaly ? (
          <Badge tone="danger">anomaly</Badge>
        ) : (
          <Badge tone="success">normal</Badge>
        )}
      </td>
    </tr>
  );
}
