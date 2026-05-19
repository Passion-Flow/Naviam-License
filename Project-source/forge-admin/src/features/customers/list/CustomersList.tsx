import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { Link } from "react-router-dom";
import { z } from "zod";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { DeleteConfirmDialog } from "@/components/DeleteConfirmDialog";
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
import { createCustomer, hardDeleteCustomer, listCustomers } from "@/lib/api/customers";
import { ApiError } from "@/lib/api/client";
import { useT } from "@/lib/i18n";
import type { CreateCustomerBody, CustomerResponse } from "@/types/api";

const createSchema = z.object({
  slug: z
    .string()
    .min(1, "slug required")
    .max(128)
    .regex(/^[a-z0-9][a-z0-9-]*$/, "lowercase letters / digits / dash only"),
  name: z.string().min(1, "name required").max(256),
  contact_email: z.string().max(256).optional().or(z.literal("")),
  contact_name: z.string().max(128).optional().or(z.literal("")),
  region: z.string().max(64).optional().or(z.literal("")),
  notes: z.string().max(10_000).optional().or(z.literal("")),
});

type CreateFormValues = z.infer<typeof createSchema>;

const customersQueryKey = ["customers", "list"] as const;

export default function CustomersListPage() {
  const t = useT();
  const [statusFilter, setStatusFilter] = React.useState<"active" | "archived" | "all">("active");
  const STATUS_FILTER_ITEMS = [
    { value: "active", label: t("customers.filter.status.active") },
    { value: "all", label: t("customers.filter.status.all") },
    { value: "archived", label: t("customers.filter.status.archived") },
  ];
  const query = useQuery({
    queryKey: [...customersQueryKey, statusFilter],
    queryFn: () =>
      listCustomers({
        limit: 200,
        status: statusFilter === "all" ? undefined : statusFilter,
      }),
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{t("page.customers.title")}</h1>
          <p className="mt-1 text-sm text-fg/60">{t("page.customers.subtitle")}</p>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-44">
            <Select
              value={statusFilter}
              onValueChange={(v) => setStatusFilter(v as "active" | "archived" | "all")}
              items={STATUS_FILTER_ITEMS}
            />
          </div>
          <CreateCustomerDialog />
        </div>
      </div>

      <Card>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-border text-sm">
            <thead className="text-left text-xs uppercase tracking-wider text-fg/60">
              <tr>
                <Th>{t("customers.col.slug")}</Th>
                <Th>{t("customers.col.name")}</Th>
                <Th>{t("customers.col.region")}</Th>
                <Th>{t("customers.col.contact")}</Th>
                <Th>{t("common.status")}</Th>
                <Th>{t("customers.col.created")}</Th>
                <Th>{t("common.actions")}</Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {query.isLoading && (
                <tr>
                  <td colSpan={7} className="px-5 py-8 text-center text-fg/50">
                    {t("common.loading")}
                  </td>
                </tr>
              )}
              {query.isError && (
                <tr>
                  <td colSpan={7} className="px-5 py-8 text-center text-red-600">
                    {t("detail.toast.load_failed")}: {(query.error as Error).message}
                  </td>
                </tr>
              )}
              {query.data?.items.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-5 py-8 text-center text-fg/50">
                    {t("customers.empty")}
                  </td>
                </tr>
              )}
              {query.data?.items.map((c) => (
                <CustomerRow key={c.id} customer={c} />
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

function Th({ children }: { children: React.ReactNode }) {
  return <th className="whitespace-nowrap px-5 py-3 font-medium">{children}</th>;
}

function CustomerRow({ customer }: { customer: CustomerResponse }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const t = useT();
  const [open, setOpen] = React.useState(false);
  const mutation = useMutation({
    mutationFn: () => hardDeleteCustomer(customer.id),
    onSuccess: () => {
      toast.show(t("delete.toast.deleted"), "success");
      queryClient.invalidateQueries({ queryKey: customersQueryKey });
      setOpen(false);
    },
    onError: (err) => toast.show(`${t("delete.toast.failed")}: ${(err as Error).message}`, "error"),
  });

  return (
    <tr className="transition-soft hover:bg-muted/40">
      <td className="whitespace-nowrap px-5 py-3 font-mono text-xs">
        <Link className="hover:underline" to={`/customers/${customer.id}`}>
          {customer.slug}
        </Link>
      </td>
      <td className="whitespace-nowrap px-5 py-3 font-medium text-fg">{customer.name}</td>
      <td className="whitespace-nowrap px-5 py-3 text-fg/70">{customer.region || "—"}</td>
      <td className="whitespace-nowrap px-5 py-3 text-fg/70">
        {customer.contact_email || customer.contact_name || "—"}
      </td>
      <td className="whitespace-nowrap px-5 py-3">
        <Badge tone={customer.status === "active" ? "success" : "neutral"}>
          {customer.status}
        </Badge>
      </td>
      <td className="whitespace-nowrap px-5 py-3 text-fg/60">
        {new Date(customer.created_at).toLocaleDateString()}
      </td>
      <td className="whitespace-nowrap px-5 py-3">
        <Button variant="danger" size="sm" onClick={() => setOpen(true)}>
          {t("delete.action")}
        </Button>
        <DeleteConfirmDialog
          open={open}
          onOpenChange={setOpen}
          cascadeWarningKey="delete.warning.customer"
          confirmField="slug"
          confirmValue={customer.slug}
          pending={mutation.isPending}
          onConfirm={() => mutation.mutate()}
        />
      </td>
    </tr>
  );
}

function CreateCustomerDialog() {
  const [open, setOpen] = React.useState(false);
  const queryClient = useQueryClient();
  const toast = useToast();
  const t = useT();
  const form = useForm<CreateFormValues>({
    defaultValues: { slug: "", name: "", contact_email: "", contact_name: "", region: "", notes: "" },
  });

  const mutation = useMutation({
    mutationFn: (body: CreateCustomerBody) => createCustomer(body),
    onSuccess: () => {
      toast.show(t("customers.toast.created"), "success");
      queryClient.invalidateQueries({ queryKey: customersQueryKey });
      setOpen(false);
      form.reset();
    },
    onError: (err) => {
      if (err instanceof ApiError && err.status === 409) {
        toast.show(t("customers.toast.slug_exists"), "error");
        form.setError("slug", { message: "slug already exists" });
        return;
      }
      toast.show(`${(err as Error).message}`, "error");
    },
  });

  const onSubmit = form.handleSubmit((data) => {
    const parsed = createSchema.safeParse(data);
    if (!parsed.success) {
      const issue = parsed.error.issues[0];
      if (issue) {
        form.setError(issue.path[0] as keyof CreateFormValues, { message: issue.message });
      }
      return;
    }
    // Strip empty strings so backend defaults kick in
    const body: CreateCustomerBody = { slug: parsed.data.slug, name: parsed.data.name };
    if (parsed.data.contact_email) body.contact_email = parsed.data.contact_email;
    if (parsed.data.contact_name) body.contact_name = parsed.data.contact_name;
    if (parsed.data.region) body.region = parsed.data.region;
    if (parsed.data.notes) body.notes = parsed.data.notes;
    mutation.mutate(body);
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>{t("customers.dialog.new")}</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogTitle>{t("customers.dialog.new")}</DialogTitle>
        <DialogDescription>
          Slug is the immutable identifier used across licenses and API keys.
        </DialogDescription>
        <form onSubmit={onSubmit} className="mt-4 space-y-4">
          <Field label="Slug" error={form.formState.errors.slug?.message}>
            <Input placeholder="acme" {...form.register("slug")} autoFocus />
          </Field>
          <Field label="Name" error={form.formState.errors.name?.message}>
            <Input placeholder="Acme Inc." {...form.register("name")} />
          </Field>
          <Field label="Contact email">
            <Input type="email" placeholder="ops@acme.test" {...form.register("contact_email")} />
          </Field>
          <Field label="Contact name">
            <Input placeholder="Jane Doe" {...form.register("contact_name")} />
          </Field>
          <Field label="Region">
            <Input placeholder="us-east" {...form.register("region")} />
          </Field>
          <div className="flex justify-end gap-2 pt-2">
            <DialogClose asChild>
              <Button type="button" variant="secondary">
                Cancel
              </Button>
            </DialogClose>
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? "Creating…" : "Create"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
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
