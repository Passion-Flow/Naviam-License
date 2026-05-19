import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/Dialog";
import { useToast } from "@/components/ui/Toast";
import { listMySessions, revokeSession } from "@/lib/api/sessions";
import { useT } from "@/lib/i18n";

/**
 * 当前用户的活跃 session 列表 + 远程踢出。当前 session 本身只能 logout 不能 revoke。
 */
export function SessionsDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}) {
  const t = useT();
  const queryClient = useQueryClient();
  const toast = useToast();

  const list = useQuery({
    queryKey: ["auth", "sessions"],
    queryFn: listMySessions,
    enabled: open,
    refetchInterval: open ? 15_000 : false,
  });

  const revokeMutation = useMutation({
    mutationFn: (prefix: string) => revokeSession(prefix),
    onSuccess: () => {
      toast.show(t("sessions.toast.revoked"), "success");
      queryClient.invalidateQueries({ queryKey: ["auth", "sessions"] });
    },
    onError: (err) =>
      toast.show(`${t("sessions.toast.failed")}: ${(err as Error).message}`, "error"),
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle>{t("sessions.title")}</DialogTitle>
        <DialogDescription>{t("sessions.subtitle")}</DialogDescription>

        <div className="mt-4 space-y-2">
          {list.isLoading && <div className="text-sm text-fg/50">{t("common.loading")}</div>}
          {list.isError && (
            <div className="text-sm text-red-600">
              {t("detail.toast.load_failed")}: {(list.error as Error).message}
            </div>
          )}
          {list.data?.items.length === 0 && (
            <div className="text-sm text-fg/50">{t("sessions.empty")}</div>
          )}
          {list.data?.items.map((s) => (
            <div
              key={s.sid_prefix}
              className="flex items-center justify-between gap-3 rounded-lg border border-border bg-bg p-3 text-sm"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs">{s.sid_prefix}…</span>
                  {s.is_current && <Badge tone="success">{t("sessions.current")}</Badge>}
                </div>
                <div className="mt-0.5 text-xs text-fg/60">
                  {t("sessions.created")}: {new Date(s.created_at).toLocaleString()}
                  {" · "}
                  {t("sessions.expires")}: {new Date(s.expires_at).toLocaleDateString()}
                </div>
              </div>
              {!s.is_current && (
                <Button
                  variant="danger"
                  size="sm"
                  onClick={() => revokeMutation.mutate(s.sid_prefix)}
                  disabled={revokeMutation.isPending}
                >
                  {t("common.revoke")}
                </Button>
              )}
            </div>
          ))}
        </div>

        <div className="mt-5 flex justify-end">
          <DialogClose asChild>
            <Button type="button">{t("common.confirm")}</Button>
          </DialogClose>
        </div>
      </DialogContent>
    </Dialog>
  );
}
