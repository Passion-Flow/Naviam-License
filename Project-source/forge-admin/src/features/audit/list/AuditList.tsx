import * as React from "react";
import { useQuery } from "@tanstack/react-query";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/Dialog";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { Select } from "@/components/ui/Select";
import { listAuditLog, type AuditLogQuery } from "@/lib/api/audit";
import { useT } from "@/lib/i18n";
import type { AuditLogEntry } from "@/types/api";

const PAGE_SIZE = 100;

// 与后端 ACTION_* 常量保持一致
const ACTION_ITEMS = [
  { value: "", label: "Any action" },
  { value: "auth.login.success", label: "auth.login.success" },
  { value: "auth.login.failure", label: "auth.login.failure" },
  { value: "auth.logout", label: "auth.logout" },
  { value: "license.issued", label: "license.issued" },
  { value: "license.revoked", label: "license.revoked" },
  { value: "license.unrevoked", label: "license.unrevoked" },
  { value: "customer.created", label: "customer.created" },
  { value: "customer.updated", label: "customer.updated" },
  { value: "customer.archived", label: "customer.archived" },
  { value: "product.created", label: "product.created" },
  { value: "product.updated", label: "product.updated" },
  { value: "key.generated", label: "key.generated" },
  { value: "key.rotated", label: "key.rotated" },
  { value: "key.revoked", label: "key.revoked" },
  { value: "apikey.issued", label: "apikey.issued" },
  { value: "apikey.revoked", label: "apikey.revoked" },
];

const TARGET_ITEMS = [
  { value: "", label: "Any target type" },
  { value: "user", label: "user" },
  { value: "license", label: "license" },
  { value: "customer", label: "customer" },
  { value: "product", label: "product" },
  { value: "api_key", label: "api_key" },
  { value: "signing_key", label: "signing_key" },
];

export default function AuditLogPage() {
  const t = useT();
  const [action, setAction] = React.useState("");
  const [targetType, setTargetType] = React.useState("");
  const [actorId, setActorId] = React.useState("");
  const [targetId, setTargetId] = React.useState("");
  const [offset, setOffset] = React.useState(0);
  const [inspecting, setInspecting] = React.useState<AuditLogEntry | null>(null);

  React.useEffect(() => {
    setOffset(0);
  }, [action, targetType, actorId, targetId]);

  const query: AuditLogQuery = {
    action: action || undefined,
    target_type: targetType || undefined,
    actor_id: actorId || undefined,
    target_id: targetId || undefined,
    limit: PAGE_SIZE,
    offset,
  };

  const list = useQuery({
    queryKey: ["audit", query],
    queryFn: () => listAuditLog(query),
    placeholderData: (prev) => prev,
  });

  const exportCsvUrl = (() => {
    const params = new URLSearchParams();
    if (action) params.set("action", action);
    if (targetType) params.set("target_type", targetType);
    if (actorId) params.set("actor_id", actorId);
    if (targetId) params.set("target_id", targetId);
    params.set("limit", "10000");
    return `/api/v1/audit/export.csv?${params.toString()}`;
  })();

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{t("page.audit.title")}</h1>
          <p className="mt-1 text-sm text-fg/60">{t("page.audit.subtitle")}</p>
        </div>
        <a href={exportCsvUrl} download>
          <Button variant="secondary">{t("audit.export_csv")}</Button>
        </a>
      </div>

      <Card className="p-5">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="space-y-1.5">
            <Label htmlFor="audit-action">{t("audit.filter.action")}</Label>
            <Select id="audit-action" value={action} onValueChange={setAction} items={ACTION_ITEMS} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="audit-target-type">{t("audit.filter.target_type")}</Label>
            <Select
              id="audit-target-type"
              value={targetType}
              onValueChange={setTargetType}
              items={TARGET_ITEMS}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="audit-actor">{t("audit.filter.actor_id")}</Label>
            <Input
              id="audit-actor"
              placeholder={t("common.any")}
              value={actorId}
              onChange={(e) => setActorId(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="audit-target">{t("audit.filter.target_id")}</Label>
            <Input
              id="audit-target"
              placeholder={t("common.any")}
              value={targetId}
              onChange={(e) => setTargetId(e.target.value)}
            />
          </div>
        </div>
      </Card>

      <Card>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-border text-sm">
            <thead className="text-left text-xs uppercase tracking-wider text-fg/60">
              <tr>
                <Th>{t("audit.col.when")}</Th>
                <Th>{t("audit.col.actor")}</Th>
                <Th>{t("audit.col.action")}</Th>
                <Th>{t("audit.col.target")}</Th>
                <Th>{t("audit.col.ip")}</Th>
                <Th className="text-right">{t("audit.col.payload")}</Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {list.isLoading && (
                <tr>
                  <td colSpan={6} className="px-5 py-8 text-center text-fg/50">
                    Loading…
                  </td>
                </tr>
              )}
              {list.isError && (
                <tr>
                  <td colSpan={6} className="px-5 py-8 text-center text-red-600">
                    Failed to load: {(list.error as Error).message}
                  </td>
                </tr>
              )}
              {list.data?.items.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-5 py-8 text-center text-fg/50">
                    No audit events match the current filters.
                  </td>
                </tr>
              )}
              {list.data?.items.map((entry) => (
                <AuditRow key={entry.id} entry={entry} onInspect={setInspecting} />
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="flex items-center justify-end gap-3 text-sm">
        <span className="text-fg/60">
          {t("licenses.page_offset")} {offset}
          {list.data?.items.length ? ` · ${t("licenses.on_page_n").replace("{n}", String(list.data.items.length))}` : ""}
        </span>
        <Button
          variant="secondary"
          size="sm"
          disabled={offset === 0}
          onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
        >
          {t("licenses.previous")}
        </Button>
        <Button
          variant="secondary"
          size="sm"
          disabled={!list.data || list.data.items.length < PAGE_SIZE}
          onClick={() => setOffset(offset + PAGE_SIZE)}
        >
          {t("licenses.next")}
        </Button>
      </div>

      <PayloadDialog entry={inspecting} onClose={() => setInspecting(null)} />
    </div>
  );
}

function Th({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <th className={`whitespace-nowrap px-5 py-3 font-medium ${className ?? ""}`}>{children}</th>;
}

function AuditRow({
  entry,
  onInspect,
}: {
  entry: AuditLogEntry;
  onInspect: (entry: AuditLogEntry) => void;
}) {
  const t = useT();
  const tone: React.ComponentProps<typeof Badge>["tone"] = entry.action.includes("failure")
    ? "danger"
    : entry.action.includes("revoked") || entry.action.includes("archived")
    ? "warning"
    : "neutral";
  return (
    <tr className="transition-soft hover:bg-muted/40">
      <td className="whitespace-nowrap px-5 py-3 text-fg/70">
        {new Date(entry.occurred_at).toLocaleString()}
      </td>
      <td className="whitespace-nowrap px-5 py-3 font-mono text-xs">
        <span className="text-fg/50">{entry.actor_type}:</span>
        {entry.actor_id}
      </td>
      <td className="whitespace-nowrap px-5 py-3">
        <Badge tone={tone}>{entry.action}</Badge>
      </td>
      <td className="whitespace-nowrap px-5 py-3 font-mono text-xs">
        <span className="text-fg/50">{entry.target_type}:</span>
        {entry.target_id}
      </td>
      <td className="whitespace-nowrap px-5 py-3 font-mono text-xs text-fg/60">
        {entry.client_ip ?? "—"}
      </td>
      <td className="whitespace-nowrap px-5 py-3 text-right">
        <Button variant="ghost" size="sm" onClick={() => onInspect(entry)}>
          {t("common.view")}
        </Button>
      </td>
    </tr>
  );
}

function PayloadDialog({
  entry,
  onClose,
}: {
  entry: AuditLogEntry | null;
  onClose: () => void;
}) {
  return (
    <Dialog open={Boolean(entry)} onOpenChange={(v) => (v ? null : onClose())}>
      <DialogContent>
        {entry && (
          <>
            <DialogTitle>Audit event #{entry.id}</DialogTitle>
            <DialogDescription>
              {entry.actor_type}:{entry.actor_id} → {entry.action} on {entry.target_type}:
              {entry.target_id}
            </DialogDescription>
            <div className="mt-4 space-y-3 text-sm">
              <Field label="Request ID" value={entry.request_id ?? "—"} mono />
              <Field label="Client IP" value={entry.client_ip ?? "—"} mono />
              <Field label="User-Agent" value={entry.user_agent ?? "—"} />
              <div>
                <div className="text-xs uppercase tracking-wider text-fg/50">Payload</div>
                <pre className="mt-1 max-h-72 overflow-auto rounded-lg border border-border bg-muted/30 p-3 font-mono text-xs">
                  {Object.keys(entry.payload ?? {}).length === 0
                    ? "(empty)"
                    : JSON.stringify(entry.payload, null, 2)}
                </pre>
              </div>
            </div>
            <div className="mt-5 flex justify-end">
              <DialogClose asChild>
                <Button type="button">Close</Button>
              </DialogClose>
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

function Field({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wider text-fg/50">{label}</div>
      <div className={mono ? "mt-0.5 break-all font-mono text-xs" : "mt-0.5"}>{value}</div>
    </div>
  );
}
