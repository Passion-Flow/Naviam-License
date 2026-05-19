import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { Link } from "react-router-dom";
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
import { useToast } from "@/components/ui/Toast";
import { ApiError } from "@/lib/api/client";
import { useT } from "@/lib/i18n";
import { createProduct, hardDeleteProduct, listProducts } from "@/lib/api/products";
import { DeleteConfirmDialog } from "@/components/DeleteConfirmDialog";
import type { CreateProductBody, ProductResponse } from "@/types/api";

const createSchema = z.object({
  slug: z
    .string()
    .min(1, "slug required")
    .max(128)
    .regex(/^[a-z0-9][a-z0-9-]*$/, "lowercase letters / digits / dash only"),
  name: z.string().min(1, "name required").max(256),
  version: z.string().max(32).optional().or(z.literal("")),
  description: z.string().max(10_000).optional().or(z.literal("")),
  features_schema_json: z.string().optional().or(z.literal("")),
  default_limits_json: z.string().optional().or(z.literal("")),
});

type CreateFormValues = z.infer<typeof createSchema>;

const productsQueryKey = ["products", "list"] as const;

function parseJsonObject(raw: string | undefined): Record<string, unknown> | undefined {
  if (!raw || raw.trim() === "") return undefined;
  const parsed: unknown = JSON.parse(raw);
  if (typeof parsed !== "object" || Array.isArray(parsed) || parsed === null) {
    throw new Error("must be a JSON object");
  }
  return parsed as Record<string, unknown>;
}

export default function ProductsListPage() {
  const t = useT();
  const query = useQuery({
    queryKey: productsQueryKey,
    queryFn: () => listProducts({ limit: 200 }),
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{t("page.products.title")}</h1>
          <p className="mt-1 text-sm text-fg/60">{t("page.products.subtitle")}</p>
        </div>
        <CreateProductDialog />
      </div>

      <Card>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-border text-sm">
            <thead className="text-left text-xs uppercase tracking-wider text-fg/60">
              <tr>
                <Th>{t("products.col.slug")}</Th>
                <Th>{t("products.col.name")}</Th>
                <Th>{t("products.col.version")}</Th>
                <Th>{t("common.status")}</Th>
                <Th>{t("products.col.created")}</Th>
                <Th>{t("common.actions")}</Th>
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
                    {t("products.empty")}
                  </td>
                </tr>
              )}
              {query.data?.items.map((p) => <ProductRow key={p.id} product={p} />)}
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

function ProductRow({ product }: { product: ProductResponse }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const t = useT();
  const [open, setOpen] = React.useState(false);
  const mutation = useMutation({
    mutationFn: () => hardDeleteProduct(product.id),
    onSuccess: () => {
      toast.show(t("delete.toast.deleted"), "success");
      queryClient.invalidateQueries({ queryKey: productsQueryKey });
      setOpen(false);
    },
    onError: (err) => toast.show(`${t("delete.toast.failed")}: ${(err as Error).message}`, "error"),
  });

  return (
    <tr className="transition-soft hover:bg-muted/40">
      <td className="whitespace-nowrap px-5 py-3 font-mono text-xs">
        <Link className="hover:underline" to={`/products/${product.id}`}>
          {product.slug}
        </Link>
      </td>
      <td className="whitespace-nowrap px-5 py-3 font-medium text-fg">{product.name}</td>
      <td className="whitespace-nowrap px-5 py-3 text-fg/70">{product.version || "—"}</td>
      <td className="whitespace-nowrap px-5 py-3">
        <Badge tone={product.status === "active" ? "success" : "neutral"}>{product.status}</Badge>
      </td>
      <td className="whitespace-nowrap px-5 py-3 text-fg/60">
        {new Date(product.created_at).toLocaleDateString()}
      </td>
      <td className="whitespace-nowrap px-5 py-3">
        <Button variant="danger" size="sm" onClick={() => setOpen(true)}>
          {t("delete.action")}
        </Button>
        <DeleteConfirmDialog
          open={open}
          onOpenChange={setOpen}
          cascadeWarningKey="delete.warning.product"
          confirmField="slug"
          confirmValue={product.slug}
          pending={mutation.isPending}
          onConfirm={() => mutation.mutate()}
        />
      </td>
    </tr>
  );
}

function CreateProductDialog() {
  const [open, setOpen] = React.useState(false);
  const queryClient = useQueryClient();
  const toast = useToast();
  const t = useT();
  const form = useForm<CreateFormValues>({
    defaultValues: {
      slug: "",
      name: "",
      version: "",
      description: "",
      features_schema_json: "",
      default_limits_json: "",
    },
  });

  const mutation = useMutation({
    mutationFn: (body: CreateProductBody) => createProduct(body),
    onSuccess: () => {
      toast.show(t("products.toast.created"), "success");
      queryClient.invalidateQueries({ queryKey: productsQueryKey });
      setOpen(false);
      form.reset();
    },
    onError: (err) => {
      if (err instanceof ApiError && err.status === 409) {
        toast.show(t("products.toast.slug_exists"), "error");
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
      if (issue) form.setError(issue.path[0] as keyof CreateFormValues, { message: issue.message });
      return;
    }
    let features: Record<string, unknown> | undefined;
    let limits: Record<string, unknown> | undefined;
    try {
      features = parseJsonObject(parsed.data.features_schema_json);
      limits = parseJsonObject(parsed.data.default_limits_json);
    } catch (err) {
      toast.show(`Invalid JSON: ${(err as Error).message}`, "error");
      return;
    }
    const body: CreateProductBody = { slug: parsed.data.slug, name: parsed.data.name };
    if (parsed.data.version) body.version = parsed.data.version;
    if (parsed.data.description) body.description = parsed.data.description;
    if (features !== undefined) body.features_schema = features;
    if (limits !== undefined) body.default_limits = limits;
    mutation.mutate(body);
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>{t("products.dialog.new")}</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogTitle>{t("products.dialog.new")}</DialogTitle>
        <DialogDescription>
          Slug is the immutable identifier referenced by issued licenses.
        </DialogDescription>
        <form onSubmit={onSubmit} className="mt-4 space-y-4">
          <Field label="Slug" error={form.formState.errors.slug?.message}>
            <Input placeholder="naviam" autoFocus {...form.register("slug")} />
          </Field>
          <Field label="Name" error={form.formState.errors.name?.message}>
            <Input placeholder="Naviam Studio" {...form.register("name")} />
          </Field>
          <Field label="Version">
            <Input placeholder="1.0.0" {...form.register("version")} />
          </Field>
          <Field label="Description">
            <Input placeholder="Short description" {...form.register("description")} />
          </Field>
          <Field label="Features schema (JSON, optional)">
            <textarea
              className="min-h-[5rem] rounded-lg border border-border bg-bg p-2 font-mono text-xs"
              placeholder='{"hd_video": "bool", "max_users": "int"}'
              {...form.register("features_schema_json")}
            />
          </Field>
          <Field label="Default limits (JSON, optional)">
            <textarea
              className="min-h-[5rem] rounded-lg border border-border bg-bg p-2 font-mono text-xs"
              placeholder='{"max_users": 100}'
              {...form.register("default_limits_json")}
            />
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
