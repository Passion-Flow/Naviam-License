import * as React from "react";

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
import { useT } from "@/lib/i18n";

/**
 * Confirmation dialog for hard-delete actions. Two-step gate:
 *  1) Show what's being deleted + cascade warning.
 *  2) Require the operator to retype the entity identifier (slug, license_id, …).
 *
 * Caller passes the actual mutation; this component only handles confirmation UX.
 */
export function DeleteConfirmDialog({
  open,
  onOpenChange,
  trigger,
  cascadeWarningKey,
  confirmField,
  confirmValue,
  pending,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  trigger?: React.ReactNode;
  /** i18n key for the cascade warning sentence (e.g. "delete.warning.customer") */
  cascadeWarningKey: string;
  /** label of the field operator must retype (e.g. "slug", "license_id") */
  confirmField: string;
  /** the exact value the operator must retype */
  confirmValue: string;
  pending: boolean;
  onConfirm: () => void;
}) {
  const t = useT();
  const [typed, setTyped] = React.useState("");
  React.useEffect(() => {
    if (!open) setTyped("");
  }, [open]);
  const matched = typed === confirmValue;
  const prompt = t("delete.confirm_text_prompt")
    .replace("{field}", confirmField)
    .replace("{value}", confirmValue);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {trigger}
      <DialogContent>
        <DialogTitle>{t("delete.dialog.title")}</DialogTitle>
        <DialogDescription>
          <span className="block font-medium text-red-600 dark:text-red-400">
            {t("delete.warning.unrecoverable")}
          </span>
          <span className="mt-2 block">{t(cascadeWarningKey)}</span>
        </DialogDescription>
        <div className="mt-4 space-y-2">
          <Label>{prompt}</Label>
          <Input
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            autoFocus
            autoComplete="off"
            spellCheck={false}
          />
          {typed.length > 0 && !matched && (
            <div className="text-xs text-red-600 dark:text-red-400">
              {t("delete.confirm_text_mismatch")}
            </div>
          )}
        </div>
        <div className="mt-5 flex justify-end gap-2">
          <DialogClose asChild>
            <Button type="button" variant="secondary">
              {t("delete.dialog.cancel")}
            </Button>
          </DialogClose>
          <Button type="button" variant="danger" disabled={!matched || pending} onClick={onConfirm}>
            {pending ? t("delete.action.deleting") : t("delete.dialog.confirm")}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
