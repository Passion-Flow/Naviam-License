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
import { useToast } from "@/components/ui/Toast";
import { useSession } from "@/hooks/useSession";
import {
  createAdminUser,
  deactivateAdminUser,
  hardDeleteAdminUser,
  listAdminUsers,
  reactivateAdminUser,
  resetAdminUserPassword,
} from "@/lib/api/adminUsers";
import { ApiError } from "@/lib/api/client";
import { DeleteConfirmDialog } from "@/components/DeleteConfirmDialog";
import { useT } from "@/lib/i18n";
import type { AdminUserEntry } from "@/types/api";

const adminsQueryKey = ["admin", "users"] as const;
const MIN_PW = 12;

const createSchema = z.object({
  username: z
    .string()
    .min(1, "username required")
    .max(64),
  email: z
    .string()
    .min(3, "email required")
    .max(256)
    .regex(/^[^@\s]+@[^@\s]+\.[^@\s]+$/, "invalid email"),
  password: z.string().min(MIN_PW, `password must be ≥ ${MIN_PW} chars`).max(512),
  is_super: z.boolean().optional(),
});
type CreateFormValues = z.infer<typeof createSchema>;

export default function AdminUsersListPage() {
  const t = useT();
  const session = useSession();
  const list = useQuery({
    queryKey: adminsQueryKey,
    queryFn: listAdminUsers,
  });

  const me = session.data;
  const meIsSuper = me?.is_super ?? false;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{t("page.admin_users.title")}</h1>
          <p className="mt-1 text-sm text-fg/60">{t("page.admin_users.subtitle")}</p>
        </div>
        {meIsSuper && <CreateUserDialog />}
      </div>

      <Card>
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-border text-sm">
            <thead className="text-left text-xs uppercase tracking-wider text-fg/60">
              <tr>
                <Th>{t("admin_users.col.username")}</Th>
                <Th>{t("admin_users.col.email")}</Th>
                <Th>{t("admin_users.col.role")}</Th>
                <Th>{t("admin_users.col.status")}</Th>
                <Th>{t("admin_users.col.last_login")}</Th>
                <Th className="text-right">{t("admin_users.col.actions")}</Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {list.isLoading && (
                <tr>
                  <td colSpan={6} className="px-5 py-8 text-center text-fg/50">
                    {t("common.loading")}
                  </td>
                </tr>
              )}
              {list.isError && (
                <tr>
                  <td colSpan={6} className="px-5 py-8 text-center text-red-600 dark:text-red-400">
                    {t("detail.toast.load_failed")}: {(list.error as Error).message}
                  </td>
                </tr>
              )}
              {list.data?.items.map((u) => (
                <Row key={u.id} entry={u} meIsSuper={meIsSuper} meId={me?.user_id} />
              ))}
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
  return (
    <th className={`whitespace-nowrap px-5 py-3 font-medium ${className ?? ""}`}>{children}</th>
  );
}

function Row({
  entry,
  meIsSuper,
  meId,
}: {
  entry: AdminUserEntry;
  meIsSuper: boolean;
  meId: string | undefined;
}) {
  const isSelf = entry.id === meId;
  const queryClient = useQueryClient();
  const toast = useToast();
  const t = useT();

  const deactivate = useMutation({
    mutationFn: () => deactivateAdminUser(entry.id),
    onSuccess: () => {
      toast.show(`${entry.username} ${t("admin_users.deactivate").toLowerCase()}`, "success");
      queryClient.invalidateQueries({ queryKey: adminsQueryKey });
    },
    onError: (err) => toast.show(`${(err as Error).message}`, "error"),
  });
  const reactivate = useMutation({
    mutationFn: () => reactivateAdminUser(entry.id),
    onSuccess: () => {
      toast.show(`${entry.username} ${t("admin_users.reactivate").toLowerCase()}`, "success");
      queryClient.invalidateQueries({ queryKey: adminsQueryKey });
    },
    onError: (err) => toast.show(`${(err as Error).message}`, "error"),
  });

  return (
    <tr className="transition-soft hover:bg-muted/40">
      <td className="whitespace-nowrap px-5 py-3 font-medium">
        {entry.username}
        {isSelf && <span className="ml-2 text-xs text-fg/50">{t("admin_users.you")}</span>}
      </td>
      <td className="whitespace-nowrap px-5 py-3 text-fg/80">{entry.email}</td>
      <td className="whitespace-nowrap px-5 py-3">
        {entry.is_super ? <Badge tone="success">super</Badge> : <Badge tone="neutral">admin</Badge>}
      </td>
      <td className="whitespace-nowrap px-5 py-3">
        {entry.is_active ? <Badge tone="success">active</Badge> : <Badge tone="danger">inactive</Badge>}
      </td>
      <td className="whitespace-nowrap px-5 py-3 text-fg/60">
        {entry.last_login_at ? new Date(entry.last_login_at).toLocaleString() : "—"}
      </td>
      <td className="whitespace-nowrap px-5 py-3 text-right">
        <div className="flex justify-end gap-2">
          {meIsSuper && !isSelf && <ResetPasswordDialog entry={entry} />}
          {meIsSuper && !isSelf && entry.is_active && (
            <Button
              variant="secondary"
              size="sm"
              onClick={() => deactivate.mutate()}
              disabled={deactivate.isPending}
            >
              {t("admin_users.deactivate")}
            </Button>
          )}
          {meIsSuper && !isSelf && !entry.is_active && (
            <Button
              variant="secondary"
              size="sm"
              onClick={() => reactivate.mutate()}
              disabled={reactivate.isPending}
            >
              {t("admin_users.reactivate")}
            </Button>
          )}
          {meIsSuper && !isSelf && <AdminUserDeleteButton entry={entry} />}
        </div>
      </td>
    </tr>
  );
}

function AdminUserDeleteButton({ entry }: { entry: AdminUserEntry }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const t = useT();
  const [open, setOpen] = React.useState(false);
  const mutation = useMutation({
    mutationFn: () => hardDeleteAdminUser(entry.id),
    onSuccess: () => {
      toast.show(t("delete.toast.deleted"), "success");
      queryClient.invalidateQueries({ queryKey: adminsQueryKey });
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
        cascadeWarningKey="delete.warning.admin_user"
        confirmField="username"
        confirmValue={entry.username}
        pending={mutation.isPending}
        onConfirm={() => mutation.mutate()}
      />
    </>
  );
}

function CreateUserDialog() {
  const [open, setOpen] = React.useState(false);
  const queryClient = useQueryClient();
  const toast = useToast();
  const t = useT();
  const form = useForm<CreateFormValues>({
    defaultValues: { username: "", email: "", password: "", is_super: false },
  });

  const mutation = useMutation({
    mutationFn: (body: CreateFormValues) =>
      createAdminUser({
        username: body.username,
        email: body.email,
        password: body.password,
        is_super: body.is_super ?? false,
      }),
    onSuccess: () => {
      toast.show("Admin created", "success");
      queryClient.invalidateQueries({ queryKey: adminsQueryKey });
      setOpen(false);
      form.reset();
    },
    onError: (err) => {
      if (err instanceof ApiError && err.status === 409) {
        toast.show(err.message, "error");
        return;
      }
      toast.show(`Create failed: ${(err as Error).message}`, "error");
    },
  });

  const onSubmit = form.handleSubmit((data) => {
    const parsed = createSchema.safeParse(data);
    if (!parsed.success) {
      const issue = parsed.error.issues[0];
      if (issue) form.setError(issue.path[0] as keyof CreateFormValues, { message: issue.message });
      return;
    }
    mutation.mutate(parsed.data);
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>{t("admin_users.dialog.add")}</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogTitle>{t("admin_users.dialog.add")}</DialogTitle>
        <DialogDescription>
          The new admin can log in immediately with the password you set. Share it out-of-band; the
          user should change it on first login.
        </DialogDescription>
        <form onSubmit={onSubmit} className="mt-4 space-y-4">
          <Field label="Username" error={form.formState.errors.username?.message}>
            <Input autoFocus {...form.register("username")} />
          </Field>
          <Field label="Email" error={form.formState.errors.email?.message}>
            <Input type="email" {...form.register("email")} />
          </Field>
          <Field label={`Initial password (≥${MIN_PW} chars)`} error={form.formState.errors.password?.message}>
            <Input type="password" autoComplete="new-password" {...form.register("password")} />
          </Field>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" {...form.register("is_super")} />
            Grant super-admin (can manage other admins)
          </label>
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

function ResetPasswordDialog({ entry }: { entry: AdminUserEntry }) {
  const [open, setOpen] = React.useState(false);
  const [pw, setPw] = React.useState("");
  const [localError, setLocalError] = React.useState<string | null>(null);
  const toast = useToast();
  const t = useT();

  const mutation = useMutation({
    mutationFn: () => resetAdminUserPassword(entry.id, { new_password: pw }),
    onSuccess: () => {
      toast.show(`${entry.username}'s password reset`, "success");
      setOpen(false);
      setPw("");
    },
    onError: (err) => {
      if (err instanceof ApiError && (err.status === 400 || err.status === 422)) {
        setLocalError(err.message || `password must be ≥ ${MIN_PW} chars`);
        return;
      }
      toast.show(`Reset failed: ${(err as Error).message}`, "error");
    },
  });

  React.useEffect(() => {
    if (!open) {
      setPw("");
      setLocalError(null);
    }
  }, [open]);

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <Button variant="ghost" size="sm" onClick={() => setOpen(true)}>
        {t("admin_users.reset_password")}
      </Button>
      <DialogContent>
        <DialogTitle>{t("admin_users.reset_password")} — {entry.username}</DialogTitle>
        <DialogDescription>
          Set a new password for this admin. They will be logged out (if currently signed in) and
          must use the new password.
        </DialogDescription>
        <div className="mt-4 space-y-2">
          <Label>New password (≥ {MIN_PW} chars)</Label>
          <Input
            type="password"
            autoComplete="new-password"
            value={pw}
            onChange={(e) => setPw(e.target.value)}
          />
          {localError && <div className="text-xs text-red-600 dark:text-red-400">{localError}</div>}
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <DialogClose asChild>
            <Button type="button" variant="secondary">
              {t("common.cancel")}
            </Button>
          </DialogClose>
          <Button
            type="button"
            disabled={pw.length < MIN_PW || mutation.isPending}
            onClick={() => {
              setLocalError(null);
              mutation.mutate();
            }}
          >
            {t("admin_users.reset_password")}
          </Button>
        </div>
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
      {error && <div className="text-xs text-red-600 dark:text-red-400">{error}</div>}
    </div>
  );
}
