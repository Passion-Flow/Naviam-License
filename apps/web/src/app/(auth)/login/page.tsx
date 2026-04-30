"use client";

import { useState } from "react";
import { Shield, Eye, EyeOff, Loader2, AlertCircle } from "lucide-react";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8081/v1";

function getCsrfToken(): string {
  if (typeof document === "undefined") return "";
  const match = document.cookie.match(/csrftoken=([^;]+)/);
  return match?.[1] ? decodeURIComponent(match[1]) : "";
}

function makeHeaders(): Record<string, string> {
  const h: Record<string, string> = { "Content-Type": "application/json" };
  const csrf = getCsrfToken();
  if (csrf) h["X-CSRFToken"] = csrf;
  return h;
}

interface AuthState {
  step: "login" | "totp" | "change_password" | "done";
  error?: string;
  loading: boolean;
  user?: { username: string; email: string };
}

export default function LoginPage() {
  const [state, setState] = useState<AuthState>({ step: "login", loading: false });
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [totpCode, setTotpCode] = useState("");

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setState({ step: "login", loading: true });
    try {
      const res = await fetch(`${API_BASE}/auth/login/`, {
        method: "POST",
        headers: makeHeaders(),
        credentials: "include",
        body: JSON.stringify({ email, password }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setState({ step: "login", loading: false, error: data.detail || "登录失败" });
        return;
      }
      if (data.requires_2fa) {
        setState({ step: "totp", loading: false });
      } else {
        setState({ step: "done", loading: false, user: data.user });
        window.location.href = "/licenses";
      }
    } catch {
      setState({ step: "login", loading: false, error: "网络错误，请检查后端服务是否启动" });
    }
  }

  async function handleTotp(e: React.FormEvent) {
    e.preventDefault();
    setState({ ...state, loading: true });
    try {
      const res = await fetch(`${API_BASE}/auth/totp/`, {
        method: "POST",
        headers: makeHeaders(),
        credentials: "include",
        body: JSON.stringify({ code: totpCode }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setState({ step: "totp", loading: false, error: data.detail || "验证码错误" });
        return;
      }
      setState({ step: "done", loading: false, user: data.user });
      window.location.href = "/licenses";
    } catch {
      setState({ step: "totp", loading: false, error: "网络错误" });
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center p-6" style={{ background: "hsl(var(--bg-secondary))" }}>
      <div className="w-full max-w-sm">
        {/* Brand */}
        <div className="mb-8 flex items-center justify-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg" style={{ background: "hsl(var(--brand-600))" }}>
            <Shield size={20} color="white" strokeWidth={2.5} />
          </div>
          <div className="text-left">
            <div className="text-base font-bold" style={{ color: "hsl(var(--text-primary))" }}>License Console</div>
            <div className="text-xs font-medium" style={{ color: "hsl(var(--text-tertiary))" }}>厂商 License 签发台</div>
          </div>
        </div>

        {/* Card */}
        <div className="surface p-6">
          {state.step === "login" && (
            <form onSubmit={handleLogin} className="space-y-4">
              <div>
                <label className="mb-1.5 block text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>
                  邮箱
                </label>
                <input
                  type="email"
                  className="input"
                  placeholder="输入邮箱"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  autoFocus
                />
              </div>
              <div>
                <label className="mb-1.5 block text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>
                  密码
                </label>
                <div className="relative">
                  <input
                    type={showPassword ? "text" : "password"}
                    className="input pr-10"
                    placeholder="输入密码"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                  />
                  <button
                    type="button"
                    className="absolute right-2.5 top-1/2 -translate-y-1/2"
                    style={{ color: "hsl(var(--text-tertiary))" }}
                    onClick={() => setShowPassword(!showPassword)}
                  >
                    {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
              </div>

              {state.error && (
                <div className="flex items-center gap-2 rounded-md px-3 py-2 text-xs font-medium" style={{ background: "hsl(var(--danger) / 0.08)", color: "hsl(var(--danger))" }}>
                  <AlertCircle size={14} />
                  {state.error}
                </div>
              )}

              <button type="submit" className="btn-primary w-full" disabled={state.loading}>
                {state.loading ? <Loader2 size={16} className="animate-spin" /> : "登录"}
              </button>
            </form>
          )}

          {state.step === "totp" && (
            <form onSubmit={handleTotp} className="space-y-4">
              <div className="text-center">
                <div className="text-sm font-semibold" style={{ color: "hsl(var(--text-primary))" }}>两步验证</div>
                <div className="mt-1 text-xs" style={{ color: "hsl(var(--text-secondary))" }}>请输入 Authenticator 应用中的 6 位验证码</div>
              </div>
              <input
                type="text"
                inputMode="numeric"
                pattern="[0-9]*"
                maxLength={8}
                className="input text-center text-lg tracking-[0.5em]"
                placeholder="000000"
                value={totpCode}
                onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, ""))}
                required
                autoFocus
              />
              {state.error && (
                <div className="flex items-center gap-2 rounded-md px-3 py-2 text-xs font-medium" style={{ background: "hsl(var(--danger) / 0.08)", color: "hsl(var(--danger))" }}>
                  <AlertCircle size={14} />
                  {state.error}
                </div>
              )}
              <button type="submit" className="btn-primary w-full" disabled={state.loading}>
                {state.loading ? <Loader2 size={16} className="animate-spin" /> : "验证"}
              </button>
            </form>
          )}
        </div>

        <div className="mt-4 text-center text-[11px] font-medium" style={{ color: "hsl(var(--text-tertiary))" }}>
          License Console v0.1.0
        </div>
      </div>
    </main>
  );
}
