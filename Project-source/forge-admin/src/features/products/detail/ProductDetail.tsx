import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { Select } from "@/components/ui/Select";
import { useToast } from "@/components/ui/Toast";
import { ApiError } from "@/lib/api/client";
import { getProduct, updateProduct } from "@/lib/api/products";
import { useT } from "@/lib/i18n";
import type { ProductResponse, UpdateProductBody } from "@/types/api";

const STATUS_ITEMS = [
  { value: "active", label: "active" },
  { value: "archived", label: "archived" },
];

export default function ProductDetailPage() {
  const { id = "" } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const toast = useToast();
  const t = useT();

  const query = useQuery({
    queryKey: ["products", "detail", id],
    queryFn: () => getProduct(id),
    enabled: Boolean(id),
    retry: (failureCount, err) => !(err instanceof ApiError && err.status === 404) && failureCount < 2,
  });

  const updateMutation = useMutation({
    mutationFn: (body: UpdateProductBody) => updateProduct(id, body),
    onSuccess: (fresh) => {
      toast.show(t("detail.toast.saved"), "success");
      queryClient.setQueryData(["products", "detail", id], fresh);
      queryClient.invalidateQueries({ queryKey: ["products", "list"] });
    },
    onError: (err) => toast.show(`${t("detail.toast.save_failed")}: ${(err as Error).message}`, "error"),
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
        <Button variant="secondary" onClick={() => navigate("/products")}>
          {t("detail.action.back_to_list")}
        </Button>
      </div>
    );
  }

  const product = query.data!;
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-xs uppercase tracking-widest text-fg/50">
            <Link to="/products" className="hover:underline">
              {t("detail.breadcrumb.products")}
            </Link>{" "}
            /
          </div>
          <h1 className="mt-1 flex items-center gap-3 text-2xl font-semibold tracking-tight">
            {product.name}
            <Badge tone={product.status === "active" ? "success" : "neutral"}>
              {product.status}
            </Badge>
          </h1>
          <div className="mt-1 font-mono text-xs text-fg/60">{product.slug}</div>
        </div>
      </div>

      <EditCard
        product={product}
        onSubmit={(body) => updateMutation.mutate(body)}
        pending={updateMutation.isPending}
      />
      <MetadataCard product={product} />
    </div>
  );
}

function EditCard({
  product,
  onSubmit,
  pending,
}: {
  product: ProductResponse;
  onSubmit: (body: UpdateProductBody) => void;
  pending: boolean;
}) {
  const toast = useToast();
  const t = useT();
  const [name, setName] = React.useState(product.name);
  const [version, setVersion] = React.useState(product.version);
  const [description, setDescription] = React.useState(product.description);
  const [status, setStatus] = React.useState<"active" | "archived">(product.status);
  const [featuresJson, setFeaturesJson] = React.useState(
    JSON.stringify(product.features_schema ?? {}, null, 2),
  );
  const [limitsJson, setLimitsJson] = React.useState(
    JSON.stringify(product.default_limits ?? {}, null, 2),
  );

  React.useEffect(() => {
    setName(product.name);
    setVersion(product.version);
    setDescription(product.description);
    setStatus(product.status);
    setFeaturesJson(JSON.stringify(product.features_schema ?? {}, null, 2));
    setLimitsJson(JSON.stringify(product.default_limits ?? {}, null, 2));
  }, [product]);

  function handleSave() {
    let features: Record<string, unknown>;
    let limits: Record<string, unknown>;
    try {
      const f = JSON.parse(featuresJson || "{}");
      const l = JSON.parse(limitsJson || "{}");
      if (typeof f !== "object" || Array.isArray(f) || f === null) throw new Error("features_schema must be an object");
      if (typeof l !== "object" || Array.isArray(l) || l === null) throw new Error("default_limits must be an object");
      features = f;
      limits = l;
    } catch (err) {
      toast.show(`Invalid JSON: ${(err as Error).message}`, "error");
      return;
    }
    onSubmit({
      name,
      version,
      description,
      status,
      features_schema: features,
      default_limits: limits,
    });
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("detail.section.profile")}</CardTitle>
      </CardHeader>
      <CardBody className="space-y-4">
        <Row label="Name">
          <Input value={name} onChange={(e) => setName(e.target.value)} />
        </Row>
        <Row label="Version">
          <Input value={version} onChange={(e) => setVersion(e.target.value)} />
        </Row>
        <Row label="Description">
          <Input value={description} onChange={(e) => setDescription(e.target.value)} />
        </Row>
        <Row label="Status">
          <Select
            value={status}
            onValueChange={(v) => setStatus(v as "active" | "archived")}
            items={STATUS_ITEMS}
          />
        </Row>
        <Row label="Features schema">
          <textarea
            className="min-h-[7rem] w-full rounded-lg border border-border bg-bg p-2 font-mono text-xs"
            value={featuresJson}
            onChange={(e) => setFeaturesJson(e.target.value)}
          />
        </Row>
        <Row label="Default limits">
          <textarea
            className="min-h-[7rem] w-full rounded-lg border border-border bg-bg p-2 font-mono text-xs"
            value={limitsJson}
            onChange={(e) => setLimitsJson(e.target.value)}
          />
        </Row>
        <div className="flex justify-end">
          <Button onClick={handleSave} disabled={pending}>
            {pending ? t("detail.action.saving") : t("detail.action.save")}
          </Button>
        </div>
      </CardBody>
    </Card>
  );
}

function MetadataCard({ product }: { product: ProductResponse }) {
  const t = useT();
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("detail.section.metadata")}</CardTitle>
      </CardHeader>
      <CardBody className="grid gap-3 text-sm sm:grid-cols-2">
        <Meta label="Product ID" value={product.id} mono />
        <Meta label="Slug" value={product.slug} mono />
        <Meta label="Created at" value={new Date(product.created_at).toLocaleString()} />
        <Meta label="Updated at" value={new Date(product.updated_at).toLocaleString()} />
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

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid items-start gap-2 sm:grid-cols-[140px_1fr]">
      <Label className="mt-2">{label}</Label>
      <div>{children}</div>
    </div>
  );
}
