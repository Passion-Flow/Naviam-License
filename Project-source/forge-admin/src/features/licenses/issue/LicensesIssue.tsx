import * as React from "react";
import { useMutation } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { Link, useNavigate } from "react-router-dom";
import { z } from "zod";

import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { Select } from "@/components/ui/Select";
import { useToast } from "@/components/ui/Toast";
import { issueLicense } from "@/lib/api/licenses";
import { useT } from "@/lib/i18n";
import type {
  BindingMode,
  IssueLicenseBody,
  LicenseScope,
  SigningAlgorithm,
  VerificationMode,
} from "@/types/api";

const issueSchema = z.object({
  customer_id: z.string().min(1, "customer_id required"),
  product_id: z.string().min(1, "product_id required"),
  mode: z.enum(["offline", "hybrid", "online"]),
  scope: z.enum(["customer_x_product", "customer_bundle", "instance"]),
  algorithm: z.enum(["ed25519", "rsa2048", "rsa4096", "sm2"]),
  binding: z.enum(["none", "soft", "hard"]),
  expires_at: z.string().min(1, "expires_at required"),
  bound_fingerprint: z.string().optional(),
  features_json: z.string().optional(),
  limits_json: z.string().optional(),
});

type IssueFormValues = z.infer<typeof issueSchema>;

const MODE_ITEMS = [
  { value: "offline", label: "offline — fully detached" },
  { value: "hybrid", label: "hybrid — offline + heartbeat" },
  { value: "online", label: "online — server-check each start" },
];
const SCOPE_ITEMS = [
  { value: "customer_x_product", label: "customer × product (one license per combo)" },
  { value: "customer_bundle", label: "customer bundle (one license, many products)" },
  { value: "instance", label: "instance (one license per deployment)" },
];
const ALGO_ITEMS = [
  { value: "ed25519", label: "ed25519 (default)" },
  { value: "rsa2048", label: "rsa2048" },
  { value: "rsa4096", label: "rsa4096" },
  { value: "sm2", label: "sm2 (国密)" },
];
const BINDING_ITEMS = [
  { value: "none", label: "none — no fingerprint binding" },
  { value: "soft", label: "soft — heartbeat-tracked" },
  { value: "hard", label: "hard — issuer-bound fingerprint" },
];

function toIsoFromDateInput(value: string): string {
  // <input type="date"> gives YYYY-MM-DD; treat as end-of-day UTC for safer expiry semantics.
  if (!value) return "";
  const [y, m, d] = value.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d, 23, 59, 59)).toISOString();
}

function parseJsonField(raw: string | undefined): Record<string, unknown> | undefined {
  if (!raw || raw.trim() === "") return undefined;
  return JSON.parse(raw); // throw on bad JSON — caller catches
}

function defaultExpiry(): string {
  const d = new Date();
  d.setUTCFullYear(d.getUTCFullYear() + 1);
  return d.toISOString().slice(0, 10);
}

export default function LicensesIssuePage() {
  const t = useT();
  const navigate = useNavigate();
  const toast = useToast();

  const form = useForm<IssueFormValues>({
    defaultValues: {
      customer_id: "",
      product_id: "",
      mode: "offline",
      scope: "instance",
      algorithm: "ed25519",
      binding: "none",
      expires_at: defaultExpiry(),
      bound_fingerprint: "",
      features_json: "",
      limits_json: "",
    },
  });

  const mutation = useMutation({
    mutationFn: (body: IssueLicenseBody) => issueLicense(body),
    onSuccess: (issued) => {
      toast.show(`Issued ${issued.license_id.slice(0, 8)}…`, "success");
      navigate(`/licenses/${issued.license_id}`);
    },
    onError: (err) => toast.show(`Issue failed: ${(err as Error).message}`, "error"),
  });

  const binding = form.watch("binding") as BindingMode;

  const onSubmit = form.handleSubmit((data) => {
    const parsed = issueSchema.safeParse(data);
    if (!parsed.success) {
      toast.show(parsed.error.issues[0]?.message ?? "Invalid form", "error");
      return;
    }
    let features: Record<string, unknown> | undefined;
    let limits: Record<string, unknown> | undefined;
    try {
      features = parseJsonField(parsed.data.features_json);
      limits = parseJsonField(parsed.data.limits_json);
    } catch (err) {
      toast.show(`Invalid JSON: ${(err as Error).message}`, "error");
      return;
    }
    if (parsed.data.binding === "hard" && !parsed.data.bound_fingerprint) {
      form.setError("bound_fingerprint", {
        message: "bound_fingerprint is required for binding=hard",
      });
      return;
    }
    const body: IssueLicenseBody = {
      customer_id: parsed.data.customer_id,
      product_id: parsed.data.product_id,
      mode: parsed.data.mode as VerificationMode,
      scope: parsed.data.scope as LicenseScope,
      algorithm: parsed.data.algorithm as SigningAlgorithm,
      binding: parsed.data.binding as BindingMode,
      expires_at: toIsoFromDateInput(parsed.data.expires_at),
    };
    if (parsed.data.bound_fingerprint) body.bound_fingerprint = parsed.data.bound_fingerprint;
    if (features !== undefined) body.features = features;
    if (limits !== undefined) body.limits = limits;
    mutation.mutate(body);
  });

  return (
    <div className="space-y-6">
      <div>
        <div className="text-xs uppercase tracking-widest text-fg/50">
          <Link to="/licenses" className="hover:underline">
            {t("detail.breadcrumb.licenses")}
          </Link>{" "}
          /
        </div>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">{t("issue.title")}</h1>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>{t("issue.section.params")}</CardTitle>
        </CardHeader>
        <CardBody>
          <form onSubmit={onSubmit} className="space-y-5">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Customer ID" error={form.formState.errors.customer_id?.message}>
                <Input placeholder="customer-slug or id" {...form.register("customer_id")} />
              </Field>
              <Field label="Product ID" error={form.formState.errors.product_id?.message}>
                <Input placeholder="product-slug" {...form.register("product_id")} />
              </Field>
              <Field label="Verification mode">
                <Select
                  value={form.watch("mode")}
                  onValueChange={(v) => form.setValue("mode", v as VerificationMode)}
                  items={MODE_ITEMS}
                />
              </Field>
              <Field label="Scope">
                <Select
                  value={form.watch("scope")}
                  onValueChange={(v) => form.setValue("scope", v as LicenseScope)}
                  items={SCOPE_ITEMS}
                />
              </Field>
              <Field label="Signing algorithm">
                <Select
                  value={form.watch("algorithm")}
                  onValueChange={(v) => form.setValue("algorithm", v as SigningAlgorithm)}
                  items={ALGO_ITEMS}
                />
              </Field>
              <Field label="Binding mode">
                <Select
                  value={form.watch("binding")}
                  onValueChange={(v) => form.setValue("binding", v as BindingMode)}
                  items={BINDING_ITEMS}
                />
              </Field>
              <Field label="Expires (UTC)" error={form.formState.errors.expires_at?.message}>
                <Input type="date" {...form.register("expires_at")} />
              </Field>
              {binding === "hard" && (
                <Field
                  label="Bound fingerprint"
                  error={form.formState.errors.bound_fingerprint?.message}
                >
                  <Input
                    placeholder="sha256 of customer deployment fingerprint"
                    {...form.register("bound_fingerprint")}
                  />
                </Field>
              )}
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Features (JSON, optional)">
                <textarea
                  className="min-h-[6rem] rounded-lg border border-border bg-bg p-2 font-mono text-xs"
                  placeholder='{"hd": true, "advanced_reports": true}'
                  {...form.register("features_json")}
                />
              </Field>
              <Field label="Limits (JSON, optional)">
                <textarea
                  className="min-h-[6rem] rounded-lg border border-border bg-bg p-2 font-mono text-xs"
                  placeholder='{"max_users": 50}'
                  {...form.register("limits_json")}
                />
              </Field>
            </div>

            <div className="flex justify-end gap-2">
              <Link to="/licenses">
                <Button type="button" variant="secondary">
                  {t("issue.action.cancel")}
                </Button>
              </Link>
              <Button type="submit" disabled={mutation.isPending}>
                {mutation.isPending ? t("issue.action.submitting") : t("issue.action.submit")}
              </Button>
            </div>
          </form>
        </CardBody>
      </Card>
    </div>
  );
}

function Field({
  label,
  error,
  children,
}: {
  label: string;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <Label>{label}</Label>
      {children}
      {error && <div className="text-xs text-red-600">{error}</div>}
    </div>
  );
}
