import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/Dialog";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { Select } from "@/components/ui/Select";
import { useToast } from "@/components/ui/Toast";
import {
  hardDeleteApiKey,
  issueApiKey,
  listApiKeys,
  revokeApiKey,
  type ApiKeyListQuery,
} from "@/lib/api/apiKeys";
import { DeleteConfirmDialog } from "@/components/DeleteConfirmDialog";
import { useT } from "@/lib/i18n";
import type { ApiKeyEntry, IssueApiKeyBody, IssueApiKeyResponse } from "@/types/api";

const STATUS_ITEMS = [
  { value: "", label: "Any status" },
  { value: "active", label: "active" },
  { value: "revoked", label: "revoked" },
];

// UI guard rail only — the real upper bound lives in
// `settings.api_key_max_expires_in_days` on the server. We pick a generous
// default (10y); if the customer set it lower, the server will reject with 422
// and we'll surface the error verbatim. Don't tighten this without a server
// endpoint to query the live limit.
const MAX_EXPIRES_IN_DAYS = 365 * 10;

const issueSchema = z.object({
  customer_id: z.string().min(1, "customer_id required").max(128),
  project_label: z.string().min(1, "project_label required").max(128),
  expires_in_days: z
    .string()
    .optional()
    .refine(
      (v) => !v || (Number.isInteger(Number(v)) && Number(v) >= 1 && Number(v) <= MAX_EXPIRES_IN_DAYS),
      `Must be 1–${MAX_EXPIRES_IN_DAYS} days, or empty for no expiry`,
    ),
});

type IssueFormValues = z.infer<typeof issueSchema>;
const apiKeysQueryKey = ["api-keys", "list"] as const;

export default function ApiKeysListPage() {
  const t = useT();
  const [statusFilter, setStatusFilter] = React.useState("");
  const [customerFilter, setCustomerFilter] = React.useState("");

  const query: ApiKeyListQuery = {
    status: (statusFilter || undefined) as ApiKeyListQuery["status"],
    customer_id: customerFilter || undefined,
    limit: 200,
  };

  const list = useQuery({
    queryKey: [...apiKeysQueryKey, query],
    queryFn: () => listApiKeys(query),
    placeholderData: (prev) => prev,
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{t("page.api_keys.title")}</h1>
          <p className="mt-1 text-sm text-fg/60">{t("page.api_keys.subtitle")}</p>
        </div>
        <IssueApiKeyDialog />
      </div>

      <Card className="p-5">
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="apikey-customer">{t("api_keys.filter.customer_id")}</Label>
            <Input
              id="apikey-customer"
              placeholder={t("common.any")}
              value={customerFilter}
              onChange={(e) => setCustomerFilter(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="apikey-status">{t("api_keys.filter.status")}</Label>
            <Select
              id="apikey-status"
              value={statusFilter}
              onValueChange={setStatusFilter}
              items={STATUS_ITEMS}
            />
          </div>
        </div>
      </Card>

      <Card>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-border text-sm">
            <thead className="text-left text-xs uppercase tracking-wider text-fg/60">
              <tr>
                <Th>{t("api_keys.col.key_id")}</Th>
                <Th>{t("api_keys.col.prefix")}</Th>
                <Th>{t("api_keys.col.customer")}</Th>
                <Th>{t("api_keys.col.project")}</Th>
                <Th>{t("api_keys.col.status")}</Th>
                <Th>{t("api_keys.col.expires")}</Th>
                <Th>{t("api_keys.col.last_used")}</Th>
                <Th>{t("api_keys.col.created")}</Th>
                <Th className="text-right">{t("api_keys.col.actions")}</Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {list.isLoading && (
                <tr>
                  <td colSpan={9} className="px-5 py-8 text-center text-fg/50">
                    {t("common.loading")}
                  </td>
                </tr>
              )}
              {list.isError && (
                <tr>
                  <td colSpan={9} className="px-5 py-8 text-center text-red-600">
                    {t("detail.toast.load_failed")}: {(list.error as Error).message}
                  </td>
                </tr>
              )}
              {list.data?.items.length === 0 && (
                <tr>
                  <td colSpan={9} className="px-5 py-8 text-center text-fg/50">
                    {t("api_keys.empty.filtered")}
                  </td>
                </tr>
              )}
              {list.data?.items.map((row) => <ApiKeyRow key={row.key_id} entry={row} />)}
            </tbody>
          </table>
        </div>
      </Card>
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

function ExpiryCell({
  expiresAt,
  status,
}: {
  expiresAt: string | null;
  status: ApiKeyEntry["status"];
}) {
  if (expiresAt === null) {
    return <span className="text-fg/40">Never</span>;
  }
  const ms = new Date(expiresAt).getTime() - Date.now();
  if (ms <= 0) {
    return (
      <span className="font-medium text-red-600 dark:text-red-400">
        Expired
      </span>
    );
  }
  const days = Math.ceil(ms / 86_400_000);
  const text = new Date(expiresAt).toLocaleDateString();
  // 已 revoked 的不再警告（已经走废）
  const warn = status === "active" && days <= 14;
  return (
    <span className={warn ? "font-medium text-amber-600 dark:text-amber-400" : ""}>
      {text}
      <span className="ml-1 text-xs text-fg/50">({days}d)</span>
    </span>
  );
}

function ApiKeyRow({ entry }: { entry: ApiKeyEntry }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const t = useT();
  const mutation = useMutation({
    mutationFn: () => revokeApiKey(entry.key_id),
    onSuccess: () => {
      toast.show(t("api_keys.action.revoked"), "success");
      queryClient.invalidateQueries({ queryKey: apiKeysQueryKey });
    },
    onError: (err) => toast.show(`${(err as Error).message}`, "error"),
  });

  return (
    <tr className="transition-soft hover:bg-muted/40">
      <td className="whitespace-nowrap px-5 py-3 font-mono text-xs">{entry.key_id}</td>
      <td className="whitespace-nowrap px-5 py-3 font-mono text-xs text-fg/80">{entry.key_prefix}…</td>
      <td className="whitespace-nowrap px-5 py-3 text-fg/80">{entry.customer_id}</td>
      <td className="whitespace-nowrap px-5 py-3 text-fg/80">{entry.project_label}</td>
      <td className="whitespace-nowrap px-5 py-3">
        <Badge tone={entry.status === "active" ? "success" : "danger"}>{entry.status}</Badge>
      </td>
      <td className="whitespace-nowrap px-5 py-3 text-fg/80">
        <ExpiryCell expiresAt={entry.expires_at} status={entry.status} />
      </td>
      <td className="whitespace-nowrap px-5 py-3 text-fg/60">
        {entry.last_used_at ? new Date(entry.last_used_at).toLocaleDateString() : "—"}
      </td>
      <td className="whitespace-nowrap px-5 py-3 text-fg/60">
        {new Date(entry.created_at).toLocaleDateString()}
      </td>
      <td className="whitespace-nowrap px-5 py-3 text-right">
        <div className="flex justify-end gap-2">
          <Button
            variant="secondary"
            size="sm"
            disabled={entry.status === "revoked" || mutation.isPending}
            onClick={() => mutation.mutate()}
          >
            {entry.status === "revoked"
              ? t("api_keys.action.revoked")
              : mutation.isPending
                ? t("api_keys.action.revoking")
                : t("common.revoke")}
          </Button>
          <DeleteButton entry={entry} />
        </div>
      </td>
    </tr>
  );
}

function DeleteButton({ entry }: { entry: ApiKeyEntry }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const t = useT();
  const [open, setOpen] = React.useState(false);
  const mutation = useMutation({
    mutationFn: () => hardDeleteApiKey(entry.key_id),
    onSuccess: () => {
      toast.show(t("delete.toast.deleted"), "success");
      queryClient.invalidateQueries({ queryKey: apiKeysQueryKey });
      setOpen(false);
    },
    onError: (err) => toast.show(`${t("delete.toast.failed")}: ${(err as Error).message}`, "error"),
  });
  return (
    <>
      <Button variant="danger" size="sm" onClick={() => setOpen(true)}>
        {t("delete.action")}
      </Button>
      <DeleteConfirmDialog
        open={open}
        onOpenChange={setOpen}
        cascadeWarningKey="delete.warning.api_key"
        confirmField="key_prefix"
        confirmValue={entry.key_prefix}
        pending={mutation.isPending}
        onConfirm={() => mutation.mutate()}
      />
    </>
  );
}

function IssueApiKeyDialog() {
  const [open, setOpen] = React.useState(false);
  const [revealed, setRevealed] = React.useState<IssueApiKeyResponse | null>(null);
  const queryClient = useQueryClient();
  const toast = useToast();
  const t = useT();
  const form = useForm<IssueFormValues>({
    defaultValues: { customer_id: "", project_label: "", expires_in_days: "" },
  });

  const mutation = useMutation({
    mutationFn: (body: IssueApiKeyBody) => issueApiKey(body),
    onSuccess: (data) => {
      toast.show(t("api_keys.toast.issued"), "success");
      queryClient.invalidateQueries({ queryKey: apiKeysQueryKey });
      setRevealed(data);
      form.reset();
    },
    onError: (err) => toast.show(`${(err as Error).message}`, "error"),
  });

  const onSubmit = form.handleSubmit((data) => {
    const parsed = issueSchema.safeParse(data);
    if (!parsed.success) {
      const issue = parsed.error.issues[0];
      if (issue) form.setError(issue.path[0] as keyof IssueFormValues, { message: issue.message });
      return;
    }
    const body: IssueApiKeyBody = {
      customer_id: parsed.data.customer_id,
      project_label: parsed.data.project_label,
    };
    if (parsed.data.expires_in_days) {
      body.expires_in_days = Number(parsed.data.expires_in_days);
    }
    mutation.mutate(body);
  });

  const close = () => {
    setOpen(false);
    setRevealed(null);
  };

  return (
    <Dialog open={open} onOpenChange={(v) => (v ? setOpen(true) : close())}>
      <DialogTrigger asChild>
        <Button>{t("api_keys.dialog.issue")}</Button>
      </DialogTrigger>
      <DialogContent>
        {revealed ? (
          <>
            <DialogTitle>{t("api_keys.dialog.copy_plaintext")}</DialogTitle>
            <DialogDescription>
              {t("api_keys.dialog.copy_warning")}
            </DialogDescription>
            <div className="mt-4 space-y-2">
              <Label>Plaintext key (one-time)</Label>
              <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 font-mono text-xs break-all text-amber-700 dark:text-amber-300">
                {revealed.plaintext}
              </div>
              <div className="text-xs text-fg/60">
                Key ID: <span className="font-mono">{revealed.key_id}</span>
              </div>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <Button
                type="button"
                variant="secondary"
                onClick={() => {
                  navigator.clipboard
                    .writeText(revealed.plaintext)
                    .then(() => toast.show(t("api_keys.toast.copied"), "success"))
                    .catch(() => toast.show(t("api_keys.toast.copy_failed"), "error"));
                }}
              >
                {t("common.copy")}
              </Button>
              <Button type="button" onClick={close}>
                {t("common.confirm")}
              </Button>
            </div>
          </>
        ) : (
          <>
            <DialogTitle>{t("api_keys.dialog.issue")}</DialogTitle>
            <DialogDescription>
              Used by verifier SDKs to authenticate against the License Authority.
            </DialogDescription>
            <form onSubmit={onSubmit} className="mt-4 space-y-4">
              <div className="space-y-1.5">
                <Label>Customer ID</Label>
                <Input placeholder="customer-slug" autoFocus {...form.register("customer_id")} />
                {form.formState.errors.customer_id && (
                  <div className="text-xs text-red-600">
                    {form.formState.errors.customer_id.message}
                  </div>
                )}
              </div>
              <div className="space-y-1.5">
                <Label>Project label</Label>
                <Input placeholder="naviam-prod" {...form.register("project_label")} />
                {form.formState.errors.project_label && (
                  <div className="text-xs text-red-600">
                    {form.formState.errors.project_label.message}
                  </div>
                )}
              </div>
              <div className="space-y-1.5">
                <Label>Expires in (days)</Label>
                <Input
                  type="number"
                  min={1}
                  max={MAX_EXPIRES_IN_DAYS}
                  placeholder="empty = never expires"
                  {...form.register("expires_in_days")}
                />
                <div className="text-xs text-fg/50">
                  Leave empty to issue a non-expiring key. Best practice: set a TTL (90–365 days)
                  and rotate before it lapses.
                </div>
                {form.formState.errors.expires_in_days && (
                  <div className="text-xs text-red-600">
                    {form.formState.errors.expires_in_days.message}
                  </div>
                )}
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <DialogClose asChild>
                  <Button type="button" variant="secondary">
                    {t("common.cancel")}
                  </Button>
                </DialogClose>
                <Button type="submit" disabled={mutation.isPending}>
                  {mutation.isPending ? t("issue.action.submitting") : t("issue.action.submit")}
                </Button>
              </div>
            </form>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
