import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { z } from "zod";

import { Button } from "@/components/ui/Button";
import { Card, CardBody } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { useToast } from "@/components/ui/Toast";
import { useSession, sessionQueryKey } from "@/hooks/useSession";
import { ApiError } from "@/lib/api/client";
import { loginRequest } from "@/lib/api/auth";
import { useT } from "@/lib/i18n";

const loginSchema = z.object({
  username: z.string().min(1, "username required").max(64),
  password: z.string().min(1, "password required").max(512),
});

type LoginForm = z.infer<typeof loginSchema>;

export default function LoginPage() {
  const queryClient = useQueryClient();
  const session = useSession();
  const navigate = useNavigate();
  const location = useLocation();
  const toast = useToast();
  const t = useT();

  const form = useForm<LoginForm>({
    defaultValues: { username: "", password: "" },
  });

  const mutation = useMutation({
    mutationFn: loginRequest,
    onSuccess: (user) => {
      queryClient.setQueryData(sessionQueryKey, user);
      const target = (location.state as { from?: string } | null)?.from ?? "/dashboard";
      navigate(target, { replace: true });
    },
    onError: (err) => {
      const msg =
        err instanceof ApiError && err.status === 401
          ? t("page.login.error.invalid")
          : t("page.login.error.generic");
      toast.show(msg, "error");
    },
  });

  if (session.isLoading) {
    return <div className="grid min-h-screen place-items-center text-sm text-fg/60">{t("page.login.loading")}</div>;
  }
  if (session.data) {
    return <Navigate to="/dashboard" replace />;
  }

  const onSubmit = form.handleSubmit((data) => {
    const parsed = loginSchema.safeParse(data);
    if (!parsed.success) {
      toast.show(parsed.error.issues[0]?.message ?? "Invalid form", "error");
      return;
    }
    mutation.mutate(parsed.data);
  });

  return (
    <main className="grid min-h-screen place-items-center bg-muted/30 px-4">
      <Card className="w-full max-w-sm">
        <CardBody className="space-y-5">
          <div className="space-y-1">
            <div className="text-xs uppercase tracking-widest text-primary">{t("app.title")}</div>
            <h1 className="text-2xl font-semibold tracking-tight text-fg">{t("page.login.title")}</h1>
            <p className="text-sm text-fg/60">{t("page.login.subtitle")}</p>
          </div>

          <form onSubmit={onSubmit} className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="username">{t("page.login.username")}</Label>
              <Input
                id="username"
                autoComplete="username"
                autoFocus
                {...form.register("username")}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="password">{t("page.login.password")}</Label>
              <Input
                id="password"
                type="password"
                autoComplete="current-password"
                {...form.register("password")}
              />
            </div>
            <Button type="submit" className="w-full" disabled={mutation.isPending}>
              {mutation.isPending ? t("page.login.signing_in") : t("page.login.submit")}
            </Button>
          </form>
        </CardBody>
      </Card>
    </main>
  );
}
