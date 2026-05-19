import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { useToast } from "@/components/ui/Toast";
import { archiveCustomer, getCustomer, updateCustomer } from "@/lib/api/customers";
import { ApiError } from "@/lib/api/client";
import { useT } from "@/lib/i18n";
import type { CustomerResponse, UpdateCustomerBody } from "@/types/api";

export default function CustomerDetailPage() {
  const { id = "" } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const toast = useToast();
  const t = useT();

  const query = useQuery({
    queryKey: ["customers", "detail", id],
    queryFn: () => getCustomer(id),
    enabled: Boolean(id),
    retry: (failureCount, err) => !(err instanceof ApiError && err.status === 404) && failureCount < 2,
  });

  const updateMutation = useMutation({
    mutationFn: (body: UpdateCustomerBody) => updateCustomer(id, body),
    onSuccess: (fresh) => {
      toast.show(t("detail.toast.saved"), "success");
      queryClient.setQueryData(["customers", "detail", id], fresh);
      queryClient.invalidateQueries({ queryKey: ["customers", "list"] });
    },
    onError: (err) => toast.show(`${t("detail.toast.save_failed")}: ${(err as Error).message}`, "error"),
  });

  const archiveMutation = useMutation({
    mutationFn: () => archiveCustomer(id),
    onSuccess: () => {
      toast.show(t("detail.toast.archived"), "success");
      queryClient.invalidateQueries({ queryKey: ["customers", "list"] });
      queryClient.invalidateQueries({ queryKey: ["customers", "detail", id] });
    },
    onError: (err) => toast.show(`${t("detail.toast.archive_failed")}: ${(err as Error).message}`, "error"),
  });

  if (query.isLoading) {
    return <div className="text-sm text-fg/60">{t("common.loading")}</div>;
  }
  if (query.isError) {
    const status = query.error instanceof ApiError ? query.error.status : null;
    return (
      <div className="space-y-3">
        <div className="text-red-600">
          {status === 404 ? t("detail.toast.not_found") : `${t("detail.toast.load_failed")}: ${(query.error as Error).message}`}
        </div>
        <Button variant="secondary" onClick={() => navigate("/customers")}>
          {t("detail.action.back_to_list")}
        </Button>
      </div>
    );
  }

  const customer = query.data!;
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-xs uppercase tracking-widest text-fg/50">
            <Link to="/customers" className="hover:underline">
              {t("detail.breadcrumb.customers")}
            </Link>{" "}
            /
          </div>
          <h1 className="mt-1 flex items-center gap-3 text-2xl font-semibold tracking-tight">
            {customer.name}
            <Badge tone={customer.status === "active" ? "success" : "neutral"}>
              {customer.status}
            </Badge>
          </h1>
          <div className="mt-1 font-mono text-xs text-fg/60">{customer.slug}</div>
        </div>
        <div className="flex gap-2">
          <Button
            variant="danger"
            disabled={customer.status === "archived" || archiveMutation.isPending}
            onClick={() => archiveMutation.mutate()}
          >
            {customer.status === "archived"
              ? t("detail.action.archived")
              : archiveMutation.isPending
                ? t("detail.action.archiving")
                : t("detail.action.archive")}
          </Button>
        </div>
      </div>

      <EditCard customer={customer} onSubmit={(body) => updateMutation.mutate(body)} pending={updateMutation.isPending} />
      <MetadataCard customer={customer} />
    </div>
  );
}

function EditCard({
  customer,
  onSubmit,
  pending,
}: {
  customer: CustomerResponse;
  onSubmit: (body: UpdateCustomerBody) => void;
  pending: boolean;
}) {
  const t = useT();
  const [form, setForm] = React.useState<UpdateCustomerBody>({
    name: customer.name,
    contact_email: customer.contact_email,
    contact_name: customer.contact_name,
    region: customer.region,
    notes: customer.notes,
  });

  React.useEffect(() => {
    setForm({
      name: customer.name,
      contact_email: customer.contact_email,
      contact_name: customer.contact_name,
      region: customer.region,
      notes: customer.notes,
    });
  }, [customer]);

  const handle = (key: keyof UpdateCustomerBody) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((prev) => ({ ...prev, [key]: e.target.value }));

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("detail.section.profile")}</CardTitle>
      </CardHeader>
      <CardBody className="space-y-4">
        <FieldRow label="Name">
          <Input value={form.name ?? ""} onChange={handle("name")} />
        </FieldRow>
        <FieldRow label="Contact email">
          <Input value={form.contact_email ?? ""} onChange={handle("contact_email")} />
        </FieldRow>
        <FieldRow label="Contact name">
          <Input value={form.contact_name ?? ""} onChange={handle("contact_name")} />
        </FieldRow>
        <FieldRow label="Region">
          <Input value={form.region ?? ""} onChange={handle("region")} />
        </FieldRow>
        <FieldRow label="Notes">
          <Input value={form.notes ?? ""} onChange={handle("notes")} />
        </FieldRow>
        <div className="flex justify-end">
          <Button onClick={() => onSubmit(form)} disabled={pending}>
            {pending ? t("detail.action.saving") : t("detail.action.save")}
          </Button>
        </div>
      </CardBody>
    </Card>
  );
}

function MetadataCard({ customer }: { customer: CustomerResponse }) {
  const t = useT();
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("detail.section.metadata")}</CardTitle>
      </CardHeader>
      <CardBody className="grid gap-3 text-sm sm:grid-cols-2">
        <Meta label="Customer ID" value={customer.id} mono />
        <Meta label="Slug" value={customer.slug} mono />
        <Meta label="Created at" value={new Date(customer.created_at).toLocaleString()} />
        <Meta label="Updated at" value={new Date(customer.updated_at).toLocaleString()} />
      </CardBody>
    </Card>
  );
}

function Meta({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wider text-fg/50">{label}</div>
      <div className={mono ? "mt-0.5 font-mono text-xs" : "mt-0.5"}>{value}</div>
    </div>
  );
}

function FieldRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid items-center gap-2 sm:grid-cols-[140px_1fr]">
      <Label>{label}</Label>
      <div>{children}</div>
    </div>
  );
}
