import * as React from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/Button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/Dialog";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { useToast } from "@/components/ui/Toast";
import { changePasswordRequest } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";
import { sessionQueryKey } from "@/hooks/useSession";

const MIN_LENGTH = 12;

/**
 * Self-service password change. After success the backend destroys the current
 * session, so we redirect to /login and clear the cached session state.
 */
export function ChangePasswordDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (next: boolean) => void;
}) {
  const [current, setCurrent] = React.useState("");
  const [next, setNext] = React.useState("");
  const [confirmNext, setConfirmNext] = React.useState("");
  const [localError, setLocalError] = React.useState<string | null>(null);

  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const toast = useToast();

  const mutation = useMutation({
    mutationFn: () =>
      changePasswordRequest({ current_password: current, new_password: next }),
    onSuccess: () => {
      toast.show("Password changed — please sign in with the new one", "success");
      queryClient.setQueryData(sessionQueryKey, null);
      queryClient.removeQueries();
      onOpenChange(false);
      navigate("/login", { replace: true });
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        if (err.status === 401) {
          setLocalError("Current password is incorrect");
          return;
        }
        if (err.status === 400) {
          setLocalError(err.message || "New password must differ from current");
          return;
        }
        if (err.status === 422) {
          setLocalError(`New password must be at least ${MIN_LENGTH} characters`);
          return;
        }
      }
      toast.show(`Change failed: ${(err as Error).message}`, "error");
    },
  });

  function submit(e: React.FormEvent) {
    e.preventDefault();
    setLocalError(null);
    if (next.length < MIN_LENGTH) {
      setLocalError(`New password must be at least ${MIN_LENGTH} characters`);
      return;
    }
    if (next !== confirmNext) {
      setLocalError("New password and confirmation do not match");
      return;
    }
    if (next === current) {
      setLocalError("New password must differ from the current one");
      return;
    }
    mutation.mutate();
  }

  // Reset state when closed
  React.useEffect(() => {
    if (!open) {
      setCurrent("");
      setNext("");
      setConfirmNext("");
      setLocalError(null);
    }
  }, [open]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogTitle>Change password</DialogTitle>
        <DialogDescription>
          You will be signed out after the change. Pick a strong password — at least{" "}
          {MIN_LENGTH} characters.
        </DialogDescription>
        <form onSubmit={submit} className="mt-4 space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="cp-current">Current password</Label>
            <Input
              id="cp-current"
              type="password"
              autoFocus
              autoComplete="current-password"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="cp-new">New password</Label>
            <Input
              id="cp-new"
              type="password"
              autoComplete="new-password"
              value={next}
              onChange={(e) => setNext(e.target.value)}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="cp-confirm">Confirm new password</Label>
            <Input
              id="cp-confirm"
              type="password"
              autoComplete="new-password"
              value={confirmNext}
              onChange={(e) => setConfirmNext(e.target.value)}
            />
          </div>
          {localError && (
            <div className="text-sm text-red-600 dark:text-red-400">{localError}</div>
          )}
          <div className="flex justify-end gap-2 pt-2">
            <DialogClose asChild>
              <Button type="button" variant="secondary">
                Cancel
              </Button>
            </DialogClose>
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? "Updating…" : "Change password"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
