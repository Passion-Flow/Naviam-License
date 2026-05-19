import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { ApiError } from "@/lib/api/client";
import { getHeartbeatDetail } from "@/lib/api/heartbeats";
import { useT } from "@/lib/i18n";

export default function HeartbeatDetailPage() {
  const { id = "" } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const t = useT();

  const query = useQuery({
    queryKey: ["heartbeats", "detail", id],
    queryFn: () => getHeartbeatDetail(id, 86_400, 200),
    enabled: Boolean(id),
    retry: (failureCount, err) =>
      !(err instanceof ApiError && err.status === 404) && failureCount < 2,
    refetchInterval: 30_000,
  });

  if (query.isLoading) return <div className="text-sm text-fg/60">{t("common.loading")}</div>;
  if (query.isError) {
    const status = query.error instanceof ApiError ? query.error.status : null;
    return (
      <div className="space-y-3">
        <div className="text-red-600">
          {status === 404
            ? t("detail.toast.not_found")
            : `${t("detail.toast.load_failed")}: ${(query.error as Error).message}`}
        </div>
        <Button variant="secondary" onClick={() => navigate("/heartbeats")}>
          {t("detail.action.back_to_list")}
        </Button>
      </div>
    );
  }

  const data = query.data!;
  return (
    <div className="space-y-6">
      <div>
        <div className="text-xs uppercase tracking-widest text-fg/50">
          <Link to="/heartbeats" className="hover:underline">
            {t("detail.breadcrumb.heartbeats")}
          </Link>{" "}
          /
        </div>
        <h1 className="mt-1 flex flex-wrap items-center gap-3 text-2xl font-semibold tracking-tight">
          <span className="font-mono text-base">{data.license_id}</span>
          <Badge tone={data.verdict.anomaly ? "danger" : "success"}>
            {data.verdict.anomaly ? "anomaly" : "normal"}
          </Badge>
        </h1>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Detector verdict</CardTitle>
        </CardHeader>
        <CardBody className="grid gap-3 text-sm sm:grid-cols-4">
          <Meta label="Anomaly" value={data.verdict.anomaly ? "yes" : "no"} />
          <Meta label="Distinct FPs" value={String(data.verdict.distinct_fingerprint_count)} />
          <Meta label="Threshold" value={String(data.verdict.threshold)} />
          <Meta
            label="Window"
            value={`${Math.round(data.verdict.window_seconds / 3600)}h`}
          />
          {data.verdict.reason && (
            <div className="sm:col-span-4">
              <div className="text-xs uppercase tracking-wider text-fg/50">Reason</div>
              <div className="mt-1 text-amber-700 dark:text-amber-300">{data.verdict.reason}</div>
            </div>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Fingerprints seen</CardTitle>
        </CardHeader>
        <CardBody className="p-0">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-border text-sm">
              <thead className="text-left text-xs uppercase tracking-wider text-fg/60">
                <tr>
                  <Th>Fingerprint</Th>
                  <Th>First seen</Th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {data.fingerprints_seen.map((fp) => (
                  <tr key={fp.fingerprint} className="transition-soft hover:bg-muted/40">
                    <td className="px-5 py-3 font-mono text-xs break-all">{fp.fingerprint}</td>
                    <td className="whitespace-nowrap px-5 py-3 text-fg/70">
                      {new Date(fp.first_seen_at).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Recent heartbeats</CardTitle>
        </CardHeader>
        <CardBody className="p-0">
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-border text-sm">
              <thead className="text-left text-xs uppercase tracking-wider text-fg/60">
                <tr>
                  <Th>Received</Th>
                  <Th>Reported</Th>
                  <Th>Fingerprint</Th>
                  <Th>API key</Th>
                  <Th>Verifier</Th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {data.recent_heartbeats.map((hb) => (
                  <tr key={hb.id} className="transition-soft hover:bg-muted/40">
                    <td className="whitespace-nowrap px-5 py-3 text-fg/70">
                      {new Date(hb.received_at).toLocaleString()}
                    </td>
                    <td className="whitespace-nowrap px-5 py-3 text-fg/60">
                      {new Date(hb.reported_at).toLocaleString()}
                    </td>
                    <td className="px-5 py-3 font-mono text-xs">
                      {hb.fingerprint.slice(0, 12)}…
                    </td>
                    <td className="whitespace-nowrap px-5 py-3 font-mono text-xs text-fg/60">
                      {hb.api_key_id ?? "—"}
                    </td>
                    <td className="whitespace-nowrap px-5 py-3 text-fg/70">
                      {hb.verifier_version || "—"}
                    </td>
                  </tr>
                ))}
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

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wider text-fg/50">{label}</div>
      <div className="mt-0.5">{value}</div>
    </div>
  );
}
