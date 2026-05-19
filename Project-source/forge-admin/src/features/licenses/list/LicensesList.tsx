import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

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
import { useToast } from "@/components/ui/Toast";
import { DeleteConfirmDialog } from "@/components/DeleteConfirmDialog";
import {
  bulkRevokeLicenses,
  hardDeleteLicense,
  listLicenses,
  type LicenseListQuery,
} from "@/lib/api/licenses";
import { useT } from "@/lib/i18n";
import type { LicenseSummary } from "@/types/api";

const PAGE_SIZE = 50;
const ALGO_ITEMS = [
  { value: "", label: "Any algorithm" },
  { value: "ed25519", label: "ed25519" },
  { value: "rsa2048", label: "rsa2048" },
  { value: "rsa4096", label: "rsa4096" },
  { value: "sm2", label: "sm2" },
];
const MODE_ITEMS = [
  { value: "", label: "Any mode" },
  { value: "offline", label: "offline" },
  { value: "hybrid", label: "hybrid" },
  { value: "online", label: "online" },
];

export default function LicensesListPage() {
  const t = useT();
  const [customerFilter, setCustomerFilter] = React.useState("");
  const [productFilter, setProductFilter] = React.useState("");
  const [algorithm, setAlgorithm] = React.useState("");
  const [mode, setMode] = React.useState("");
  const [search, setSearch] = React.useState("");
  const [offset, setOffset] = React.useState(0);
  const [selected, setSelected] = React.useState<Set<string>>(new Set());

  // Reset offset/selection when filters change
  React.useEffect(() => {
    setOffset(0);
    setSelected(new Set());
  }, [customerFilter, productFilter, algorithm, mode, search]);

  const query: LicenseListQuery = {
    customer_id: customerFilter || undefined,
    product_id: productFilter || undefined,
    algorithm: algorithm || undefined,
    mode: mode || undefined,
    q: search || undefined,
    limit: PAGE_SIZE,
    offset,
  };

  const list = useQuery({
    queryKey: ["licenses", "list", query],
    queryFn: () => listLicenses(query),
    placeholderData: (prev) => prev,
  });

  const toggleOne = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  const toggleAllOnPage = () => {
    const ids = list.data?.items.map((r) => r.license_id) ?? [];
    setSelected((prev) => {
      const allSelected = ids.every((id) => prev.has(id));
      const next = new Set(prev);
      if (allSelected) ids.forEach((id) => next.delete(id));
      else ids.forEach((id) => next.add(id));
      return next;
    });
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{t("page.licenses.title")}</h1>
          <p className="mt-1 text-sm text-fg/60">{t("page.licenses.subtitle")}</p>
        </div>
        <div className="flex items-center gap-2">
          {selected.size > 0 && (
            <BulkRevokeDialog
              licenseIds={Array.from(selected)}
              onDone={() => setSelected(new Set())}
            />
          )}
          <Link to="/licenses/issue">
            <Button>{t("page.licenses.issue")}</Button>
          </Link>
        </div>
      </div>

      <Card className="p-5">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          <div className="space-y-1.5 lg:col-span-2">
            <Label htmlFor="filter-search">{t("common.search")}</Label>
            <Input
              id="filter-search"
              placeholder={t("page.licenses.search_placeholder")}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="filter-customer">{t("page.licenses.filter.customer")}</Label>
            <Input
              id="filter-customer"
              placeholder={t("common.any")}
              value={customerFilter}
              onChange={(e) => setCustomerFilter(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="filter-product">{t("page.licenses.filter.product")}</Label>
            <Input
              id="filter-product"
              placeholder={t("common.any")}
              value={productFilter}
              onChange={(e) => setProductFilter(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="filter-algo">{t("page.licenses.filter.algorithm")}</Label>
            <Select id="filter-algo" value={algorithm} onValueChange={setAlgorithm} items={ALGO_ITEMS} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="filter-mode">{t("page.licenses.filter.mode")}</Label>
            <Select id="filter-mode" value={mode} onValueChange={setMode} items={MODE_ITEMS} />
          </div>
        </div>
      </Card>

      <Card>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-border text-sm">
            <thead className="text-left text-xs uppercase tracking-wider text-fg/60">
              <tr>
                <th className="px-3 py-3">
                  <input
                    type="checkbox"
                    aria-label="select all on page"
                    checked={
                      !!list.data?.items.length &&
                      list.data.items.every((r) => selected.has(r.license_id))
                    }
                    onChange={toggleAllOnPage}
                  />
                </th>
                <Th>{t("page.licenses.col.license_id")}</Th>
                <Th>{t("page.licenses.col.customer")}</Th>
                <Th>{t("page.licenses.col.product")}</Th>
                <Th>{t("page.licenses.col.mode")}</Th>
                <Th>{t("page.licenses.col.algorithm")}</Th>
                <Th>{t("page.licenses.col.binding")}</Th>
                <Th>{t("page.licenses.col.expires")}</Th>
                <Th>{t("common.actions")}</Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {list.isLoading && (
                <tr>
                  <td colSpan={9} className="px-5 py-8 text-center text-fg/50">
                    Loading…
                  </td>
                </tr>
              )}
              {list.isError && (
                <tr>
                  <td colSpan={9} className="px-5 py-8 text-center text-red-600">
                    Failed to load: {(list.error as Error).message}
                  </td>
                </tr>
              )}
              {list.data?.items.length === 0 && (
                <tr>
                  <td colSpan={9} className="px-5 py-8 text-center text-fg/50">
                    {t("licenses.empty.filtered")}
                  </td>
                </tr>
              )}
              {list.data?.items.map((row) => (
                <LicenseRow
                  key={row.license_id}
                  row={row}
                  selected={selected.has(row.license_id)}
                  onToggle={() => toggleOne(row.license_id)}
                />
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <div className="flex items-center justify-between gap-3 text-sm">
        <span className="text-fg/60">
          {selected.size > 0
            ? t("licenses.selected_n").replace("{n}", String(selected.size))
            : list.data?.items.length
              ? t("licenses.on_page_n").replace("{n}", String(list.data.items.length))
              : ""}
        </span>
        <div className="flex items-center gap-3">
          <span className="text-fg/60">{t("licenses.page_offset")} {offset}</span>
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
      </div>
    </div>
  );
}

function Th({ children }: { children: React.ReactNode }) {
  return <th className="whitespace-nowrap px-5 py-3 font-medium">{children}</th>;
}

function LicenseRow({
  row,
  selected,
  onToggle,
}: {
  row: LicenseSummary;
  selected: boolean;
  onToggle: () => void;
}) {
  const expiresAt = new Date(row.expires_at);
  const expired = expiresAt.getTime() < Date.now();
  const queryClient = useQueryClient();
  const toast = useToast();
  const t = useT();
  const [open, setOpen] = React.useState(false);
  const mutation = useMutation({
    mutationFn: () => hardDeleteLicense(row.license_id),
    onSuccess: () => {
      toast.show(t("delete.toast.deleted"), "success");
      queryClient.invalidateQueries({ queryKey: ["licenses", "list"] });
      setOpen(false);
    },
    onError: (err) => toast.show(`${t("delete.toast.failed")}: ${(err as Error).message}`, "error"),
  });
  return (
    <tr className="transition-soft hover:bg-muted/40">
      <td className="px-3 py-3">
        <input
          type="checkbox"
          aria-label={`select ${row.license_id}`}
          checked={selected}
          onChange={onToggle}
        />
      </td>
      <td className="px-5 py-3 font-mono text-xs">
        <Link className="hover:underline" to={`/licenses/${row.license_id}`}>
          {row.license_id.slice(0, 10)}…
        </Link>
      </td>
      <td className="whitespace-nowrap px-5 py-3 text-fg/80">{row.customer_id}</td>
      <td className="whitespace-nowrap px-5 py-3 text-fg/80">{row.product_id}</td>
      <td className="whitespace-nowrap px-5 py-3">
        <Badge tone="neutral">{row.mode}</Badge>
      </td>
      <td className="whitespace-nowrap px-5 py-3 text-fg/80">{row.algorithm}</td>
      <td className="whitespace-nowrap px-5 py-3 text-fg/80">{row.binding}</td>
      <td className="whitespace-nowrap px-5 py-3 text-fg/70">
        {expiresAt.toLocaleDateString()}{" "}
        {row.is_revoked && <Badge tone="danger">revoked</Badge>}
        {!row.is_revoked && expired && <Badge tone="warning">expired</Badge>}
      </td>
      <td className="whitespace-nowrap px-5 py-3">
        <Button variant="danger" size="sm" onClick={() => setOpen(true)}>
          {t("delete.action")}
        </Button>
        <DeleteConfirmDialog
          open={open}
          onOpenChange={setOpen}
          cascadeWarningKey="delete.warning.license"
          confirmField="license_id"
          confirmValue={row.license_id}
          pending={mutation.isPending}
          onConfirm={() => mutation.mutate()}
        />
      </td>
    </tr>
  );
}

function BulkRevokeDialog({
  licenseIds,
  onDone,
}: {
  licenseIds: string[];
  onDone: () => void;
}) {
  const [open, setOpen] = React.useState(false);
  const [reason, setReason] = React.useState("");
  const queryClient = useQueryClient();
  const toast = useToast();
  const t = useT();
  const mutation = useMutation({
    mutationFn: () => bulkRevokeLicenses({ license_ids: licenseIds, reason }),
    onSuccess: (r) => {
      toast.show(
        `Revoked ${r.revoked_count} · not found ${r.not_found_count} · already ${r.already_revoked_count}`,
        "success",
      );
      queryClient.invalidateQueries({ queryKey: ["licenses", "list"] });
      setOpen(false);
      setReason("");
      onDone();
    },
    onError: (err) => toast.show(`Bulk revoke failed: ${(err as Error).message}`, "error"),
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <Button variant="danger" size="sm" onClick={() => setOpen(true)}>
        {t("page.licenses.bulk_revoke_n").replace("{n}", String(licenseIds.length))}
      </Button>
      <DialogContent>
        <DialogTitle>{t("licenses.bulk_revoke_dialog_title").replace("{n}", String(licenseIds.length))}</DialogTitle>
        <DialogDescription>
          Revoked licenses can no longer be heart-beated. End-customer apps in `hybrid` /
          `online` mode start failing at next recheck. This action is recorded in audit log
          as a single bulk event.
        </DialogDescription>
        <div className="mt-4 space-y-2">
          <Label>Reason (audit only)</Label>
          <Input
            placeholder="e.g. contract terminated, security incident"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <DialogClose asChild>
            <Button type="button" variant="secondary">{t("common.cancel")}</Button>
          </DialogClose>
          <Button
            type="button"
            variant="danger"
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending}
          >
            {mutation.isPending
              ? t("licenses.bulk_revoking")
              : t("page.licenses.bulk_revoke_n").replace("{n}", String(licenseIds.length))}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
