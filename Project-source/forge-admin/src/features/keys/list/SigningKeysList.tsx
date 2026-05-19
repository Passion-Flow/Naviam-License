import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

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
  generateSigningKey,
  hardDeleteSigningKey,
  listSigningKeys,
  revokeSigningKey,
  rotateSigningKey,
} from "@/lib/api/signingKeys";
import { DeleteConfirmDialog } from "@/components/DeleteConfirmDialog";
import { useT } from "@/lib/i18n";
import type {
  GenerateSigningKeyBody,
  SigningAlgorithm,
  SigningKeyResponse,
} from "@/types/api";

const ALGO_FILTER_ITEMS = [
  { value: "", label: "Any algorithm" },
  { value: "ed25519", label: "ed25519" },
  { value: "rsa2048", label: "rsa2048" },
  { value: "rsa4096", label: "rsa4096" },
  { value: "sm2", label: "sm2" },
];
const STATUS_FILTER_ITEMS = [
  { value: "", label: "Any status" },
  { value: "active", label: "active" },
  { value: "rotated", label: "rotated" },
  { value: "revoked", label: "revoked" },
];
const ALGO_GEN_ITEMS = [
  { value: "ed25519", label: "ed25519 (default)" },
  { value: "rsa2048", label: "rsa2048" },
  { value: "rsa4096", label: "rsa4096" },
  { value: "sm2", label: "sm2 (国密)" },
];

// 算法说明 —— 展示在 Generate 对话框 + View 详情里
const ALGO_INFO: Record<
  SigningAlgorithm,
  { name: string; size: string; speed: string; note: string }
> = {
  ed25519: {
    name: "Ed25519",
    size: "32 B 公钥 / 64 B 签名",
    speed: "签 ≈ 60μs / 验 ≈ 200μs",
    note: "推荐默认：曲线安全、签名快、密钥小；与 RFC 8032 一致。",
  },
  rsa2048: {
    name: "RSA-PSS 2048",
    size: "270 B 公钥 / 256 B 签名",
    speed: "签 ≈ 1ms / 验 ≈ 150μs",
    note: "FIPS / 老平台兼容场景；签名比 Ed25519 大 4×。",
  },
  rsa4096: {
    name: "RSA-PSS 4096",
    size: "550 B 公钥 / 512 B 签名",
    speed: "签 ≈ 7ms / 验 ≈ 300μs",
    note: "高强度合规场景；签名时长比 2048 慢 7×。",
  },
  sm2: {
    name: "SM2 (国密 GM/T 0003.2)",
    size: "65 B 公钥 / 64 B 签名",
    speed: "签 ≈ 1.5ms / 验 ≈ 3ms",
    note: "中国商密合规客户专用；依赖 gmssl 库。",
  },
};

const keysQueryKey = ["signing-keys", "list"] as const;

export default function SigningKeysListPage() {
  const t = useT();
  const [algorithm, setAlgorithm] = React.useState("");
  const [statusFilter, setStatusFilter] = React.useState("");

  const list = useQuery({
    queryKey: [...keysQueryKey, { algorithm, statusFilter }],
    queryFn: () =>
      listSigningKeys({
        algorithm: algorithm || undefined,
        status: statusFilter || undefined,
      }),
    placeholderData: (prev) => prev,
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{t("page.signing_keys.title")}</h1>
          <p className="mt-1 text-sm text-fg/60">{t("page.signing_keys.subtitle")}</p>
        </div>
        <GenerateKeyDialog />
      </div>

      <Card className="p-5">
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="key-algo">{t("signing_keys.filter.algorithm")}</Label>
            <Select
              id="key-algo"
              value={algorithm}
              onValueChange={setAlgorithm}
              items={ALGO_FILTER_ITEMS}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="key-status">{t("signing_keys.filter.status")}</Label>
            <Select
              id="key-status"
              value={statusFilter}
              onValueChange={setStatusFilter}
              items={STATUS_FILTER_ITEMS}
            />
          </div>
        </div>
      </Card>

      <Card>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-border text-sm">
            <thead className="text-left text-xs uppercase tracking-wider text-fg/60">
              <tr>
                <Th>{t("signing_keys.col.key_id")}</Th>
                <Th>{t("signing_keys.col.algorithm")}</Th>
                <Th>{t("signing_keys.col.status")}</Th>
                <Th>{t("signing_keys.col.created")}</Th>
                <Th>{t("signing_keys.col.activated")}</Th>
                <Th>{t("signing_keys.col.rotated")}</Th>
                <Th className="text-right">{t("signing_keys.col.actions")}</Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {list.isLoading && (
                <tr>
                  <td colSpan={7} className="px-5 py-8 text-center text-fg/50">
                    {t("common.loading")}
                  </td>
                </tr>
              )}
              {list.isError && (
                <tr>
                  <td colSpan={7} className="px-5 py-8 text-center text-red-600">
                    {t("detail.toast.load_failed")}: {(list.error as Error).message}
                  </td>
                </tr>
              )}
              {list.data?.items.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-5 py-8 text-center text-fg/50">
                    {t("signing_keys.empty.filtered")}
                  </td>
                </tr>
              )}
              {list.data?.items.map((row) => <KeyRow key={row.key_id} entry={row} />)}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

function Th({ children, className }: { children: React.ReactNode; className?: string }) {
  return <th className={`whitespace-nowrap px-5 py-3 font-medium ${className ?? ""}`}>{children}</th>;
}

function KeyRow({ entry }: { entry: SigningKeyResponse }) {
  const tone =
    entry.status === "active" ? "success" : entry.status === "rotated" ? "neutral" : "danger";
  return (
    <tr className="transition-soft hover:bg-muted/40">
      <td className="whitespace-nowrap px-5 py-3 font-mono text-xs">{entry.key_id}</td>
      <td className="whitespace-nowrap px-5 py-3 text-fg/80">{entry.algorithm}</td>
      <td className="whitespace-nowrap px-5 py-3">
        <Badge tone={tone}>{entry.status}</Badge>
      </td>
      <td className="whitespace-nowrap px-5 py-3 text-fg/60">
        {new Date(entry.created_at).toLocaleDateString()}
      </td>
      <td className="whitespace-nowrap px-5 py-3 text-fg/60">
        {entry.activated_at ? new Date(entry.activated_at).toLocaleDateString() : "—"}
      </td>
      <td className="whitespace-nowrap px-5 py-3 text-fg/60">
        {entry.rotated_at ? new Date(entry.rotated_at).toLocaleDateString() : "—"}
      </td>
      <td className="whitespace-nowrap px-5 py-3 text-right">
        <div className="flex justify-end gap-2">
          <ViewPublicKeyDialog entry={entry} />
          {entry.status === "active" && <RotateButton keyId={entry.key_id} />}
          {entry.status !== "revoked" && <RevokeButton keyId={entry.key_id} />}
          <KeyDeleteButton entry={entry} />
        </div>
      </td>
    </tr>
  );
}

function GenerateKeyDialog() {
  const [open, setOpen] = React.useState(false);
  const [algorithm, setAlgorithm] = React.useState<SigningAlgorithm>("ed25519");
  const [activate, setActivate] = React.useState(true);
  const queryClient = useQueryClient();
  const toast = useToast();
  const t = useT();
  const mutation = useMutation({
    mutationFn: (body: GenerateSigningKeyBody) => generateSigningKey(body),
    onSuccess: (key) => {
      toast.show(t("signing_keys.toast.generated").replace("{key_id}", key.key_id.slice(0, 10)), "success");
      queryClient.invalidateQueries({ queryKey: keysQueryKey });
      setOpen(false);
    },
    onError: (err) => toast.show(`${(err as Error).message}`, "error"),
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>{t("page.signing_keys.generate")}</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogTitle>{t("signing_keys.dialog.generate")}</DialogTitle>
        <DialogDescription>
          {t("page.signing_keys.subtitle")}
        </DialogDescription>
        <div className="mt-4 space-y-4">
          <div className="space-y-1.5">
            <Label>{t("signing_keys.filter.algorithm")}</Label>
            <Select
              value={algorithm}
              onValueChange={(v) => setAlgorithm(v as SigningAlgorithm)}
              items={ALGO_GEN_ITEMS}
            />
          </div>
          <AlgorithmInfo algorithm={algorithm} />
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={activate}
              onChange={(e) => setActivate(e.target.checked)}
            />
            {t("signing_keys.dialog.activate_now")}
          </label>
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <DialogClose asChild>
            <Button type="button" variant="secondary">
              {t("common.cancel")}
            </Button>
          </DialogClose>
          <Button
            type="button"
            onClick={() => mutation.mutate({ algorithm, activate })}
            disabled={mutation.isPending}
          >
            {mutation.isPending ? t("signing_keys.action.generating") : t("signing_keys.action.generate")}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function RotateButton({ keyId }: { keyId: string }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const t = useT();
  const mutation = useMutation({
    mutationFn: () => rotateSigningKey(keyId),
    onSuccess: (result) => {
      toast.show(t("signing_keys.toast.rotated").replace("{key_id}", result.new_key.key_id.slice(0, 10)), "success");
      queryClient.invalidateQueries({ queryKey: keysQueryKey });
    },
    onError: (err) => toast.show(`${(err as Error).message}`, "error"),
  });
  return (
    <Button variant="secondary" size="sm" onClick={() => mutation.mutate()} disabled={mutation.isPending}>
      {mutation.isPending ? t("signing_keys.action.rotating") : t("signing_keys.action.rotate")}
    </Button>
  );
}

function RevokeButton({ keyId }: { keyId: string }) {
  const [open, setOpen] = React.useState(false);
  const [reason, setReason] = React.useState("");
  const queryClient = useQueryClient();
  const toast = useToast();
  const t = useT();
  const mutation = useMutation({
    mutationFn: () => revokeSigningKey(keyId, reason),
    onSuccess: () => {
      toast.show(t("api_keys.action.revoked"), "success");
      queryClient.invalidateQueries({ queryKey: keysQueryKey });
      setOpen(false);
    },
    onError: (err) => toast.show(`${(err as Error).message}`, "error"),
  });
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <Button variant="danger" size="sm" onClick={() => setOpen(true)}>
        {t("common.revoke")}
      </Button>
      <DialogContent>
        <DialogTitle>{t("signing_keys.dialog.revoke")}</DialogTitle>
        <DialogDescription>
          {t("page.signing_keys.subtitle")}
        </DialogDescription>
        <div className="mt-4 space-y-2">
          <Label>Reason (audit only)</Label>
          <Input
            placeholder="e.g. compromised, scheduled retirement"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <DialogClose asChild>
            <Button type="button" variant="secondary">
              {t("common.cancel")}
            </Button>
          </DialogClose>
          <Button
            type="button"
            variant="danger"
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending}
          >
            {mutation.isPending ? t("signing_keys.action.revoking") : t("signing_keys.action.confirm_revoke")}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function AlgorithmInfo({ algorithm }: { algorithm: SigningAlgorithm }) {
  const info = ALGO_INFO[algorithm];
  if (!info) return null;
  return (
    <div className="rounded-lg border border-border bg-muted/30 p-3 text-xs text-fg/80">
      <div className="font-semibold text-fg">{info.name}</div>
      <div className="mt-1 grid grid-cols-2 gap-x-3 gap-y-0.5">
        <span className="text-fg/55">size</span><span className="font-mono">{info.size}</span>
        <span className="text-fg/55">perf</span><span className="font-mono">{info.speed}</span>
      </div>
      <div className="mt-1.5 text-fg/65">{info.note}</div>
    </div>
  );
}

async function sha256Hex(b64: string): Promise<string> {
  const raw = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
  const digest = await crypto.subtle.digest("SHA-256", raw);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("")
    .toUpperCase()
    .match(/.{2}/g)!
    .join(":");
}

function ViewPublicKeyDialog({ entry }: { entry: SigningKeyResponse }) {
  const [open, setOpen] = React.useState(false);
  const [fingerprint, setFingerprint] = React.useState<string>("");
  const toast = useToast();
  const t = useT();
  React.useEffect(() => {
    if (!open) return;
    sha256Hex(entry.public_key_b64)
      .then(setFingerprint)
      .catch(() => setFingerprint("(fingerprint unavailable)"));
  }, [open, entry.public_key_b64]);

  const algoInfo = ALGO_INFO[entry.algorithm as SigningAlgorithm];

  const download = () => {
    const blob = new Blob([entry.public_key_b64], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${entry.key_id}.${entry.algorithm}.pub.b64`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <Button variant="ghost" size="sm" onClick={() => setOpen(true)}>
        {t("signing_keys.action.view")}
      </Button>
      <DialogContent>
        <DialogTitle>{t("signing_keys.dialog.public_key")}</DialogTitle>
        <DialogDescription>
          Share this base64 blob with verifier SDKs that pin a specific signing key.
        </DialogDescription>
        <div className="mt-4 space-y-3">
          <div className="text-xs text-fg/60">
            Key ID: <span className="font-mono">{entry.key_id}</span>
          </div>
          {algoInfo && <AlgorithmInfo algorithm={entry.algorithm as SigningAlgorithm} />}
          <div className="space-y-1">
            <Label>SHA-256 fingerprint</Label>
            <div className="rounded-lg border border-border bg-muted/20 p-2 font-mono text-[11px] break-all text-fg/80">
              {fingerprint || "computing…"}
            </div>
          </div>
          <div className="space-y-1">
            <Label>Public key (base64)</Label>
            <pre className="max-h-56 overflow-auto rounded-lg border border-border bg-muted/30 p-3 font-mono text-xs break-all">
              {entry.public_key_b64}
            </pre>
          </div>
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <Button
            type="button"
            variant="secondary"
            onClick={() =>
              navigator.clipboard
                .writeText(entry.public_key_b64)
                .then(() => toast.show("Copied", "success"))
                .catch(() => toast.show("Copy failed", "error"))
            }
          >
            Copy
          </Button>
          <Button type="button" variant="secondary" onClick={download}>
            Download
          </Button>
          <DialogClose asChild>
            <Button type="button">Close</Button>
          </DialogClose>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function KeyDeleteButton({ entry }: { entry: SigningKeyResponse }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const t = useT();
  const [open, setOpen] = React.useState(false);
  const mutation = useMutation({
    mutationFn: () => hardDeleteSigningKey(entry.key_id),
    onSuccess: () => {
      toast.show(t("delete.toast.deleted"), "success");
      queryClient.invalidateQueries({ queryKey: keysQueryKey });
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
        cascadeWarningKey="delete.warning.signing_key"
        confirmField="key_id"
        confirmValue={entry.key_id}
        pending={mutation.isPending}
        onConfirm={() => mutation.mutate()}
      />
    </>
  );
}
