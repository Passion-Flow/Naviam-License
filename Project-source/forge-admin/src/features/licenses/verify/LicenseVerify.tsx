import * as React from "react";
import { useMutation } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { useToast } from "@/components/ui/Toast";
import { verifyLicense, type VerifyLicenseResponse } from "@/lib/api/licenses";
import { useT } from "@/lib/i18n";

const STATUS_TONE: Record<
  VerifyLicenseResponse["status"],
  React.ComponentProps<typeof Badge>["tone"]
> = {
  valid: "success",
  expired: "warning",
  revoked: "danger",
  binding_mismatch: "danger",
  signature_invalid: "danger",
  unknown_key: "danger",
  malformed: "danger",
};

function statusHintKey(s: VerifyLicenseResponse["status"]): string {
  switch (s) {
    case "valid": return "verify.status.hint.valid";
    case "expired": return "verify.status.hint.expired";
    case "revoked": return "verify.status.hint.revoked";
    case "binding_mismatch": return "verify.status.hint.fingerprint_mismatch";
    case "signature_invalid": return "verify.status.hint.signature_invalid";
    case "unknown_key": return "verify.status.hint.algorithm_unsupported";
    case "malformed": return "verify.status.hint.malformed";
    default: return "verify.status.hint.malformed";
  }
}

/**
 * Paste a base64 .forge string OR drop a .forge file; we POST it to /licenses/verify
 * and render the structured result. Useful for support / forensics work.
 */
export default function LicenseVerifyPage() {
  const t = useT();
  const [base64, setBase64] = React.useState("");
  const [fingerprint, setFingerprint] = React.useState("");
  const [result, setResult] = React.useState<VerifyLicenseResponse | null>(null);
  const toast = useToast();

  const mutation = useMutation({
    mutationFn: () =>
      verifyLicense({
        forge_file_b64: base64.trim(),
        deployment_fingerprint: fingerprint.trim() || undefined,
      }),
    onSuccess: (data) => setResult(data),
    onError: (err) => toast.show(t("verify.toast.verify_failed").replace("{msg}", (err as Error).message), "error"),
  });

  function handleFile(file: File) {
    const reader = new FileReader();
    reader.onload = () => {
      const buf = reader.result;
      if (typeof buf === "string") {
        toast.show(t("verify.toast.file_not_binary"), "error");
        return;
      }
      if (!buf) return;
      const bytes = new Uint8Array(buf as ArrayBuffer);
      let binary = "";
      for (let i = 0; i < bytes.length; i += 1024) {
        binary += String.fromCharCode(...bytes.subarray(i, i + 1024));
      }
      setBase64(btoa(binary));
      toast.show(
        t("verify.toast.file_loaded")
          .replace("{name}", file.name)
          .replace("{bytes}", String(bytes.length)),
        "success",
      );
    };
    reader.onerror = () => toast.show(t("verify.toast.read_failed"), "error");
    reader.readAsArrayBuffer(file);
  }

  function onDrop(ev: React.DragEvent<HTMLDivElement>) {
    ev.preventDefault();
    const file = ev.dataTransfer.files?.[0];
    if (file) handleFile(file);
  }

  function onPick(ev: React.ChangeEvent<HTMLInputElement>) {
    const file = ev.target.files?.[0];
    if (file) handleFile(file);
    ev.target.value = "";
  }

  return (
    <div className="space-y-6">
      <div>
        <div className="text-xs uppercase tracking-widest text-fg/50">
          <Link to="/licenses" className="hover:underline">
            {t("detail.breadcrumb.licenses")}
          </Link>{" "}
          /
        </div>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">{t("page.verify.title")}</h1>
        <p className="mt-1 text-sm text-fg/60">{t("page.verify.subtitle")}</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{t("verify.section.input")}</CardTitle>
        </CardHeader>
        <CardBody className="space-y-4">
          <div
            onDragOver={(e) => e.preventDefault()}
            onDrop={onDrop}
            className="rounded-xl border-2 border-dashed border-border p-6 text-center transition-soft hover:border-primary/50"
          >
            <div className="text-sm text-fg/70">{t("verify.dropzone")}</div>
            <div className="mt-1 text-xs text-fg/50">{t("verify.or")}</div>
            <label className="mt-3 inline-flex">
              <input type="file" className="hidden" accept=".forge,application/octet-stream" onChange={onPick} />
              <span className="cursor-pointer rounded-lg border border-border bg-bg px-3 py-1.5 text-sm transition-soft hover:bg-muted">
                {t("verify.pick_file")}
              </span>
            </label>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="verify-b64">{t("verify.field.forge_b64")}</Label>
            <textarea
              id="verify-b64"
              className="min-h-[10rem] w-full rounded-lg border border-border bg-bg p-3 font-mono text-xs"
              placeholder={t("verify.field.forge_b64_placeholder")}
              value={base64}
              onChange={(e) => setBase64(e.target.value)}
            />
            <div className="text-xs text-fg/50">{base64.length.toLocaleString()} {t("verify.chars_suffix")}</div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="verify-fp">{t("verify.field.fingerprint")}</Label>
            <Input
              id="verify-fp"
              placeholder={t("verify.field.fingerprint_placeholder")}
              value={fingerprint}
              onChange={(e) => setFingerprint(e.target.value)}
            />
          </div>

          <div className="flex justify-end gap-2">
            <Button
              variant="secondary"
              onClick={() => {
                setBase64("");
                setFingerprint("");
                setResult(null);
              }}
            >
              {t("verify.action.clear")}
            </Button>
            <Button
              onClick={() => mutation.mutate()}
              disabled={!base64.trim() || mutation.isPending}
            >
              {mutation.isPending ? t("verify.action.verifying") : t("verify.action.verify")}
            </Button>
          </div>
        </CardBody>
      </Card>

      {result && (
        <Card>
          <CardHeader>
            <CardTitle>{t("verify.section.result")}</CardTitle>
          </CardHeader>
          <CardBody className="space-y-4">
            <div className="flex items-center gap-3">
              <Badge tone={STATUS_TONE[result.status]}>{result.status}</Badge>
              <span className="text-sm text-fg/70">{t(statusHintKey(result.status))}</span>
            </div>
            <div className="grid gap-3 text-sm sm:grid-cols-2">
              <Meta
                label={t("verify.field.license_id")}
                value={result.license_id ?? "—"}
                mono
                linkTo={result.license_id ? `/licenses/${result.license_id}` : undefined}
              />
              <Meta
                label={t("verify.field.valid_until")}
                value={result.valid_until ? new Date(result.valid_until).toLocaleString() : "—"}
              />
              <Meta
                label={t("verify.field.server_time")}
                value={new Date(result.server_time).toLocaleString()}
              />
              <Meta label={t("verify.field.reason")} value={result.reason ?? "—"} />
            </div>
          </CardBody>
        </Card>
      )}
    </div>
  );
}

function Meta({
  label,
  value,
  mono = false,
  linkTo,
}: {
  label: string;
  value: string;
  mono?: boolean;
  linkTo?: string;
}) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wider text-fg/50">{label}</div>
      {linkTo ? (
        <Link to={linkTo} className="mt-0.5 block break-all font-mono text-xs hover:underline">
          {value}
        </Link>
      ) : (
        <div className={mono ? "mt-0.5 break-all font-mono text-xs" : "mt-0.5"}>{value}</div>
      )}
    </div>
  );
}
