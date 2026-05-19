import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/Dialog";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { useToast } from "@/components/ui/Toast";
import { ApiError } from "@/lib/api/client";
import {
  downloadLicense,
  getLicense,
  renewLicense,
  revokeLicense,
  unrevokeLicense,
} from "@/lib/api/licenses";
import { useT } from "@/lib/i18n";
import type { LicenseDetail } from "@/types/api";

export default function LicenseDetailPage() {
  const { id = "" } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const toast = useToast();
  const t = useT();

  const detailKey = ["licenses", "detail", id] as const;
  const detail = useQuery<LicenseDetail, Error>({
    queryKey: detailKey,
    queryFn: () => getLicense(id),
    enabled: Boolean(id),
    retry: (failureCount, err) =>
      !(err instanceof ApiError && err.status === 404) && failureCount < 2,
  });

  const downloadMutation = useMutation({
    mutationFn: () => downloadLicense(id),
    onSuccess: (blob) => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${id}.forge`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      toast.show("Downloaded", "success");
    },
    onError: (err) => toast.show(`Download failed: ${(err as Error).message}`, "error"),
  });

  const unrevokeMutation = useMutation({
    mutationFn: () => unrevokeLicense(id),
    onSuccess: () => {
      toast.show("Re-activated", "success");
      queryClient.invalidateQueries({ queryKey: detailKey });
    },
    onError: (err) => toast.show(`Unrevoke failed: ${(err as Error).message}`, "error"),
  });

  if (detail.isLoading) {
    return <div className="text-sm text-fg/60">{t("common.loading")}</div>;
  }
  if (detail.isError) {
    const status = detail.error instanceof ApiError ? detail.error.status : null;
    return (
      <div className="space-y-3">
        <div className="text-red-600">
          {status === 404
            ? t("detail.toast.not_found")
            : `${t("detail.toast.load_failed")}: ${(detail.error as Error).message}`}
        </div>
        <Button variant="secondary" onClick={() => navigate("/licenses")}>
          {t("detail.action.back_to_list")}
        </Button>
      </div>
    );
  }

  const lic = detail.data!;
  const expiresAt = new Date(lic.expires_at);
  const expired = expiresAt.getTime() < Date.now();

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-xs uppercase tracking-widest text-fg/50">
            <Link to="/licenses" className="hover:underline">
              {t("detail.breadcrumb.licenses")}
            </Link>{" "}
            /
          </div>
          <h1 className="mt-1 flex flex-wrap items-center gap-3 text-2xl font-semibold tracking-tight">
            <span className="font-mono text-base text-fg/90">{lic.license_id}</span>
            <Badge tone={lic.revoked ? "danger" : expired ? "warning" : "success"}>
              {lic.revoked ? "revoked" : expired ? "expired" : "active"}
            </Badge>
          </h1>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="secondary"
            onClick={() => downloadMutation.mutate()}
            disabled={downloadMutation.isPending}
          >
            {downloadMutation.isPending ? `${t("detail.action.download_forge")}…` : t("detail.action.download_forge")}
          </Button>
          <RenewDialog licenseId={lic.license_id} currentExpiresAt={lic.expires_at} />
          {lic.revoked ? (
            <Button
              variant="secondary"
              onClick={() => unrevokeMutation.mutate()}
              disabled={unrevokeMutation.isPending}
            >
              {unrevokeMutation.isPending ? "Reactivating…" : "Reactivate"}
            </Button>
          ) : (
            <RevokeDialog licenseId={lic.license_id} />
          )}
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>License</CardTitle>
        </CardHeader>
        <CardBody className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-3">
          <Meta label="Customer" value={lic.customer_id} />
          <Meta label="Product" value={lic.product_id} />
          <Meta label="Mode" value={lic.mode} />
          <Meta label="Scope" value={lic.scope} />
          <Meta label="Algorithm" value={lic.algorithm} />
          <Meta label="Binding" value={lic.binding} />
          <Meta label="Signing key" value={lic.signing_key_id} mono />
          <Meta label="Bound fingerprint" value={lic.bound_fingerprint ?? "—"} mono />
          <Meta label="Issued at" value={new Date(lic.issued_at).toLocaleString()} />
          <Meta label="Expires at" value={expiresAt.toLocaleString()} />
        </CardBody>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Features &amp; limits</CardTitle>
        </CardHeader>
        <CardBody className="grid gap-4 sm:grid-cols-2">
          <JsonBox title="Features" data={lic.features} />
          <JsonBox title="Limits" data={lic.limits} />
        </CardBody>
      </Card>
    </div>
  );
}

function Meta({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wider text-fg/50">{label}</div>
      <div className={mono ? "mt-0.5 break-all font-mono text-xs" : "mt-0.5"}>{value}</div>
    </div>
  );
}

function JsonBox({ title, data }: { title: string; data: Record<string, unknown> }) {
  const empty = Object.keys(data ?? {}).length === 0;
  return (
    <div>
      <div className="text-xs uppercase tracking-wider text-fg/50">{title}</div>
      <pre className="mt-1 max-h-48 overflow-auto rounded-lg border border-border bg-muted/30 p-3 font-mono text-xs">
        {empty ? "(empty)" : JSON.stringify(data, null, 2)}
      </pre>
    </div>
  );
}

function RevokeDialog({ licenseId }: { licenseId: string }) {
  const [open, setOpen] = React.useState(false);
  const [reason, setReason] = React.useState("");
  const queryClient = useQueryClient();
  const toast = useToast();
  const mutation = useMutation({
    mutationFn: () => revokeLicense(licenseId, reason),
    onSuccess: () => {
      toast.show("Revoked", "success");
      queryClient.invalidateQueries({ queryKey: ["licenses", "detail", licenseId] });
      queryClient.invalidateQueries({ queryKey: ["licenses", "list"] });
      setOpen(false);
    },
    onError: (err) => toast.show(`Revoke failed: ${(err as Error).message}`, "error"),
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <Button variant="danger" onClick={() => setOpen(true)}>
        Revoke
      </Button>
      <DialogContent>
        <DialogTitle>Revoke license</DialogTitle>
        <DialogDescription>
          The license will be added to the CRL. Verifiers refresh the CRL on schedule; existing
          deployments may continue to validate until then.
        </DialogDescription>
        <div className="mt-4 space-y-2">
          <Label htmlFor="revoke-reason">Reason (audit only)</Label>
          <Input
            id="revoke-reason"
            placeholder="e.g. customer-requested"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <DialogClose asChild>
            <Button type="button" variant="secondary">
              Cancel
            </Button>
          </DialogClose>
          <Button
            type="button"
            variant="danger"
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending}
          >
            {mutation.isPending ? "Revoking…" : "Confirm revoke"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function RenewDialog({
  licenseId,
  currentExpiresAt,
}: {
  licenseId: string;
  currentExpiresAt: string;
}) {
  const [open, setOpen] = React.useState(false);
  const [newDate, setNewDate] = React.useState(() => {
    const d = new Date(currentExpiresAt);
    d.setUTCFullYear(d.getUTCFullYear() + 1);
    return d.toISOString().slice(0, 10);
  });
  const [revokeOld, setRevokeOld] = React.useState(true);
  const navigate = useNavigate();
  const toast = useToast();
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: () =>
      renewLicense(licenseId, {
        expires_at: new Date(`${newDate}T23:59:59Z`).toISOString(),
        revoke_old: revokeOld,
      }),
    onSuccess: (renewed) => {
      toast.show(`Renewed → ${renewed.new_license_id.slice(0, 8)}…`, "success");
      queryClient.invalidateQueries({ queryKey: ["licenses", "list"] });
      setOpen(false);
      navigate(`/licenses/${renewed.new_license_id}`);
    },
    onError: (err) => toast.show(`Renew failed: ${(err as Error).message}`, "error"),
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <Button variant="secondary" onClick={() => setOpen(true)}>
        Renew
      </Button>
      <DialogContent>
        <DialogTitle>Renew license</DialogTitle>
        <DialogDescription>
          Issue a new license for the same customer / product with an extended expiry. The
          original can optionally be revoked atomically.
        </DialogDescription>
        <div className="mt-4 space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="renew-date">New expiry (UTC)</Label>
            <Input
              id="renew-date"
              type="date"
              value={newDate}
              onChange={(e) => setNewDate(e.target.value)}
            />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={revokeOld}
              onChange={(e) => setRevokeOld(e.target.checked)}
            />
            Revoke the previous license
          </label>
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <DialogClose asChild>
            <Button type="button" variant="secondary">
              Cancel
            </Button>
          </DialogClose>
          <Button
            type="button"
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending}
          >
            {mutation.isPending ? "Renewing…" : "Renew"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
