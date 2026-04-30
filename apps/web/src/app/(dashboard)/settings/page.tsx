"use client";

import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle,
  Check,
  Clock,
  Copy,
  Eye,
  EyeOff,
  Globe,
  KeyRound,
  Loader2,
  Lock,
  Shield,
  Smartphone,
} from "lucide-react";
import Modal from "@/components/Modal";
import { api, type LoginAttempt } from "@/lib/api";

interface CurrentUser {
  id: string;
  username: string;
  email: string;
  is_superadmin: boolean;
  must_change_pw: boolean;
  totp_confirmed: boolean;
  created_at: string;
}

interface SecuritySettings {
  password: {
    hasher: string;
    min_length: number;
    can_change: boolean;
  };
  totp: {
    enabled: boolean;
    can_setup: boolean;
    can_disable: boolean;
    issuer: string;
  };
  session: {
    duration_hours: number;
    lockout_limit: number;
    lockout_minutes: number;
    user_rate_limit: string;
    csrf_enabled: boolean;
    csrf_same_site: string;
  };
  signing: {
    algorithm: string;
    kid: string;
    backend: string;
    audit_enabled: boolean;
    audit_kid: string;
  };
}

interface TotpSetup {
  secret: string;
  uri: string;
}

interface TotpConfirmResponse {
  detail: string;
  recovery_codes: string[];
}

function formatTime(iso: string | null | undefined) {
  if (!iso) return "-";
  const d = new Date(iso);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function parseUA(ua: string | null) {
  if (!ua) return { browser: "-", os: "-" };
  let browser = "Unknown";
  let os = "Unknown";
  if (ua.includes("Chrome")) browser = "Chrome";
  else if (ua.includes("Firefox")) browser = "Firefox";
  else if (ua.includes("Safari")) browser = "Safari";
  else if (ua.includes("Edge")) browser = "Edge";
  if (ua.includes("Windows")) os = "Windows";
  else if (ua.includes("Mac")) os = "macOS";
  else if (ua.includes("Linux")) os = "Linux";
  else if (ua.includes("Android")) os = "Android";
  else if (ua.includes("iPhone") || ua.includes("iPad")) os = "iOS";
  return { browser, os };
}

function shortId(id: string | undefined) {
  if (!id) return "-";
  return `${id.slice(0, 8)}...${id.slice(-6)}`;
}

function InfoRow({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span style={{ color: "hsl(var(--text-secondary))" }}>{label}</span>
      <div className="min-w-0 text-right">{children}</div>
    </div>
  );
}

const RESULT_LABELS: Record<string, { label: string; cls: string }> = {
  success: { label: "成功", cls: "badge-success" },
  bad_password: { label: "密码错误", cls: "badge-danger" },
  locked: { label: "已锁定", cls: "badge-warning" },
  "2fa_failed": { label: "2FA 失败", cls: "badge-warning" },
};

const LOGIN_HISTORY_PAGE_SIZE = 10;

export default function SettingsPage() {
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [security, setSecurity] = useState<SecuritySettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [loginHistory, setLoginHistory] = useState<LoginAttempt[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyPage, setHistoryPage] = useState(1);
  const [copiedAccountId, setCopiedAccountId] = useState(false);
  const [copiedTotp, setCopiedTotp] = useState<"secret" | "uri" | null>(null);

  const [pwOpen, setPwOpen] = useState(false);
  const [oldPw, setOldPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [confirmPw, setConfirmPw] = useState("");
  const [pwError, setPwError] = useState("");
  const [pwSuccess, setPwSuccess] = useState("");
  const [pwLoading, setPwLoading] = useState(false);
  const [showPw, setShowPw] = useState(false);

  const [totpOpen, setTotpOpen] = useState(false);
  const [totpSetup, setTotpSetup] = useState<TotpSetup | null>(null);
  const [totpCode, setTotpCode] = useState("");
  const [totpError, setTotpError] = useState("");
  const [totpLoading, setTotpLoading] = useState(false);
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([]);

  const [disableTotpOpen, setDisableTotpOpen] = useState(false);
  const [disableTotpPassword, setDisableTotpPassword] = useState("");
  const [disableTotpError, setDisableTotpError] = useState("");
  const [disableTotpLoading, setDisableTotpLoading] = useState(false);

  const minPasswordLength = security?.password.min_length ?? 12;

  const fetchInitial = useCallback(async () => {
    setLoading(true);
    setHistoryLoading(true);
    try {
      const [userData, securityData, historyData] = await Promise.all([
        api.get<CurrentUser>("/auth/me/"),
        api.get<SecuritySettings>("/settings/security/"),
        api.get<LoginAttempt[]>("/auth/login-history/"),
      ]);
      setUser(userData);
      setSecurity(securityData);
      setLoginHistory(historyData);
    } finally {
      setLoading(false);
      setHistoryLoading(false);
    }
  }, []);

  const refreshSecurity = useCallback(async () => {
    const [userData, securityData] = await Promise.all([
      api.get<CurrentUser>("/auth/me/"),
      api.get<SecuritySettings>("/settings/security/"),
    ]);
    setUser(userData);
    setSecurity(securityData);
  }, []);

  useEffect(() => {
    fetchInitial();
  }, [fetchInitial]);

  useEffect(() => {
    setHistoryPage(1);
  }, [loginHistory.length]);

  const historyPageCount = Math.max(1, Math.ceil(loginHistory.length / LOGIN_HISTORY_PAGE_SIZE));
  const currentHistoryPage = Math.min(historyPage, historyPageCount);
  const historyStart = (currentHistoryPage - 1) * LOGIN_HISTORY_PAGE_SIZE;
  const visibleLoginHistory = loginHistory.slice(
    historyStart,
    historyStart + LOGIN_HISTORY_PAGE_SIZE
  );

  const copyText = async (value: string, onDone: () => void) => {
    await navigator.clipboard.writeText(value);
    onDone();
    window.setTimeout(() => {
      setCopiedAccountId(false);
      setCopiedTotp(null);
    }, 1500);
  };

  const openTotpSetup = async () => {
    setTotpOpen(true);
    setTotpError("");
    setTotpCode("");
    setRecoveryCodes([]);
    setTotpSetup(null);
    setTotpLoading(true);
    try {
      const data = await api.get<TotpSetup>("/auth/totp/setup/");
      setTotpSetup(data);
    } catch (err: any) {
      setTotpError(err.detail || "无法创建两步验证密钥");
    } finally {
      setTotpLoading(false);
    }
  };

  const handleConfirmTotp = async (e: React.FormEvent) => {
    e.preventDefault();
    setTotpError("");
    setTotpLoading(true);
    try {
      const data = await api.post<TotpConfirmResponse>("/auth/totp/setup/", { code: totpCode });
      setRecoveryCodes(data.recovery_codes || []);
      await refreshSecurity();
    } catch (err: any) {
      setTotpError(err.detail || "验证码无效");
    } finally {
      setTotpLoading(false);
    }
  };

  const handleDisableTotp = async (e: React.FormEvent) => {
    e.preventDefault();
    setDisableTotpError("");
    setDisableTotpLoading(true);
    try {
      await api.post("/auth/totp/disable/", { password: disableTotpPassword });
      setDisableTotpOpen(false);
      setDisableTotpPassword("");
      await refreshSecurity();
    } catch (err: any) {
      setDisableTotpError(err.detail || "密码错误，无法关闭两步验证");
    } finally {
      setDisableTotpLoading(false);
    }
  };

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setPwError("");
    setPwSuccess("");
    if (newPw !== confirmPw) {
      setPwError("两次输入的新密码不一致");
      return;
    }
    if (newPw.length < minPasswordLength) {
      setPwError(`密码长度至少 ${minPasswordLength} 位`);
      return;
    }
    setPwLoading(true);
    try {
      await api.post("/auth/change-password/", { old_password: oldPw, new_password: newPw });
      setPwSuccess("密码修改成功，请重新登录");
      setOldPw("");
      setNewPw("");
      setConfirmPw("");
      setTimeout(() => {
        window.location.href = "/login";
      }, 2000);
    } catch (err: any) {
      setPwError(err.detail || "旧密码不正确或新密码不符合要求");
    } finally {
      setPwLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 size={24} className="animate-spin" style={{ color: "hsl(var(--text-tertiary))" }} />
      </div>
    );
  }

  return (
    <div className="p-6 space-y-5">
      <div>
        <h1 className="text-xl font-bold" style={{ color: "hsl(var(--text-primary))" }}>设置</h1>
        <p className="mt-0.5 text-xs font-medium" style={{ color: "hsl(var(--text-secondary))" }}>
          个人信息、安全设置与登录历史
        </p>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <div className="surface p-5">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg" style={{ background: "hsl(var(--brand-50))" }}>
              <Globe size={20} style={{ color: "hsl(var(--brand-600))" }} />
            </div>
            <div>
              <div className="text-sm font-bold" style={{ color: "hsl(var(--text-primary))" }}>个人信息</div>
              <div className="text-xs font-medium" style={{ color: "hsl(var(--text-secondary))" }}>账号基本信息</div>
            </div>
          </div>
          <div className="mt-4 space-y-3 text-xs">
            <InfoRow label="用户名">
              <span className="font-mono font-semibold" style={{ color: "hsl(var(--text-primary))" }}>{user?.username || "-"}</span>
            </InfoRow>
            <InfoRow label="邮箱">
              <span className="font-mono font-semibold" style={{ color: "hsl(var(--text-primary))" }}>{user?.email || "-"}</span>
            </InfoRow>
            <InfoRow label="角色">
              <span className={`badge ${user?.is_superadmin ? "badge-info" : "badge-neutral"}`}>
                {user?.is_superadmin ? "超级管理员" : "普通用户"}
              </span>
            </InfoRow>
            <InfoRow label="账号 ID">
              <div className="flex min-w-0 items-center justify-end gap-1.5">
                <span
                  className="truncate font-mono text-[10px]"
                  style={{ color: "hsl(var(--text-tertiary))", maxWidth: "13rem" }}
                  title={user?.id || ""}
                >
                  {shortId(user?.id)}
                </span>
                {user?.id && (
                  <button
                    type="button"
                    className="rounded p-1 transition-colors hover:bg-gray-100"
                    style={{ color: "hsl(var(--text-tertiary))" }}
                    title="复制完整账号 ID"
                    onClick={() => copyText(user.id, () => setCopiedAccountId(true))}
                  >
                    {copiedAccountId ? <Check size={12} /> : <Copy size={12} />}
                  </button>
                )}
              </div>
            </InfoRow>
            <InfoRow label="创建时间">
              <span className="font-mono text-[10px]" style={{ color: "hsl(var(--text-tertiary))" }}>{formatTime(user?.created_at)}</span>
            </InfoRow>
          </div>
        </div>

        <div className="surface p-5">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg" style={{ background: "hsl(var(--success) / 0.08)" }}>
              <Shield size={20} style={{ color: "hsl(var(--success))" }} />
            </div>
            <div>
              <div className="text-sm font-bold" style={{ color: "hsl(var(--text-primary))" }}>安全状态</div>
              <div className="text-xs font-medium" style={{ color: "hsl(var(--text-secondary))" }}>2FA / 密码策略</div>
            </div>
          </div>
          <div className="mt-4 space-y-3 text-xs">
            <InfoRow label="两步验证 (TOTP)">
              <div className="flex items-center justify-end gap-2">
                <span className={`badge ${user?.totp_confirmed ? "badge-success" : "badge-neutral"}`}>
                  {user?.totp_confirmed ? "已启用" : "未启用"}
                </span>
                {user?.totp_confirmed ? (
                  <button className="btn-secondary px-2 py-1 text-xs" onClick={() => setDisableTotpOpen(true)}>
                    关闭
                  </button>
                ) : (
                  <button className="btn-secondary px-2 py-1 text-xs" onClick={openTotpSetup}>
                    启用
                  </button>
                )}
              </div>
            </InfoRow>
            <InfoRow label="密码哈希">
              <span className="font-semibold" style={{ color: "hsl(var(--text-primary))" }}>{security?.password.hasher || "-"}</span>
            </InfoRow>
            <InfoRow label="最小密码长度">
              <span className="font-semibold" style={{ color: "hsl(var(--text-primary))" }}>{minPasswordLength} 位</span>
            </InfoRow>
            <InfoRow label="强制改密">
              <span className={`badge ${user?.must_change_pw ? "badge-warning" : "badge-success"}`}>
                {user?.must_change_pw ? "是" : "否"}
              </span>
            </InfoRow>
            <button
              className="btn-primary mt-3 w-full text-xs"
              onClick={() => setPwOpen(true)}
              disabled={!security?.password.can_change}
            >
              <Lock size={14} />
              修改密码
            </button>
          </div>
        </div>

        <div className="surface p-5">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg" style={{ background: "hsl(var(--info) / 0.08)" }}>
              <Clock size={20} style={{ color: "hsl(var(--info))" }} />
            </div>
            <div>
              <div className="text-sm font-bold" style={{ color: "hsl(var(--text-primary))" }}>会话策略</div>
              <div className="text-xs font-medium" style={{ color: "hsl(var(--text-secondary))" }}>Cookie / 锁定 / 限流</div>
            </div>
          </div>
          <div className="mt-4 space-y-3 text-xs">
            <InfoRow label="Session 有效期">
              <span className="font-semibold" style={{ color: "hsl(var(--text-primary))" }}>{security?.session.duration_hours ?? "-"} 小时</span>
            </InfoRow>
            <InfoRow label="失败锁定">
              <span className="font-semibold" style={{ color: "hsl(var(--text-primary))" }}>
                {security ? `${security.session.lockout_limit} 次 / ${security.session.lockout_minutes} 分钟` : "-"}
              </span>
            </InfoRow>
            <InfoRow label="登录限流">
              <span className="font-semibold" style={{ color: "hsl(var(--text-primary))" }}>{security?.session.user_rate_limit || "-"}</span>
            </InfoRow>
            <InfoRow label="CSRF 保护">
              <span className={`badge ${security?.session.csrf_enabled ? "badge-success" : "badge-danger"}`}>
                {security?.session.csrf_enabled ? "已启用" : "未启用"}
              </span>
            </InfoRow>
          </div>
        </div>

        <div className="surface p-5">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg" style={{ background: "hsl(var(--brand-50))" }}>
              <KeyRound size={20} style={{ color: "hsl(var(--brand-600))" }} />
            </div>
            <div>
              <div className="text-sm font-bold" style={{ color: "hsl(var(--text-primary))" }}>签发密钥</div>
              <div className="text-xs font-medium" style={{ color: "hsl(var(--text-secondary))" }}>License 签名配置</div>
            </div>
          </div>
          <div className="mt-4 space-y-3 text-xs">
            <InfoRow label="算法">
              <span className="font-semibold" style={{ color: "hsl(var(--text-primary))" }}>{security?.signing.algorithm || "-"}</span>
            </InfoRow>
            <InfoRow label="当前 kid">
              <span className="font-mono font-semibold" style={{ color: "hsl(var(--text-primary))" }}>{security?.signing.kid || "-"}</span>
            </InfoRow>
            <InfoRow label="后端存储">
              <span className="font-semibold" style={{ color: "hsl(var(--text-primary))" }}>{security?.signing.backend || "-"}</span>
            </InfoRow>
            <InfoRow label="审计签名">
              <span className={`badge ${security?.signing.audit_enabled ? "badge-success" : "badge-danger"}`}>
                {security?.signing.audit_enabled ? "已启用" : "未启用"}
              </span>
            </InfoRow>
          </div>
        </div>
      </div>

      <div className="surface overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b" style={{ borderColor: "hsl(var(--border))" }}>
          <div className="flex items-center gap-2">
            <Smartphone size={16} style={{ color: "hsl(var(--text-secondary))" }} />
            <span className="text-sm font-bold" style={{ color: "hsl(var(--text-primary))" }}>登录历史</span>
          </div>
          <span className="text-xs" style={{ color: "hsl(var(--text-tertiary))" }}>最近 50 条，每页 10 条</span>
        </div>
        {historyLoading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 size={24} className="animate-spin" style={{ color: "hsl(var(--text-tertiary))" }} />
          </div>
        ) : loginHistory.length === 0 ? (
          <div className="px-5 py-8 text-center">
            <div className="text-xs font-medium" style={{ color: "hsl(var(--text-tertiary))" }}>暂无登录记录</div>
          </div>
        ) : (
          <>
            <table className="w-full text-sm">
              <thead>
                <tr style={{ background: "hsl(var(--bg-secondary))" }}>
                  <th className="px-4 py-3 text-left text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>时间</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>IP</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>浏览器</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>系统</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>结果</th>
                </tr>
              </thead>
              <tbody>
                {visibleLoginHistory.map((h) => {
                  const ua = parseUA(h.ua);
                  const result = RESULT_LABELS[h.result] || { label: h.result, cls: "badge-neutral" };
                  return (
                    <tr key={h.id} className="border-t" style={{ borderColor: "hsl(var(--border))" }}>
                      <td className="px-4 py-3 text-xs font-mono whitespace-nowrap" style={{ color: "hsl(var(--text-secondary))" }}>
                        {formatTime(h.created_at)}
                      </td>
                      <td className="px-4 py-3 text-xs font-mono" style={{ color: "hsl(var(--text-secondary))" }}>{h.ip}</td>
                      <td className="px-4 py-3 text-xs" style={{ color: "hsl(var(--text-secondary))" }}>{ua.browser}</td>
                      <td className="px-4 py-3 text-xs" style={{ color: "hsl(var(--text-secondary))" }}>{ua.os}</td>
                      <td className="px-4 py-3">
                        <span className={`badge ${result.cls} text-[10px]`}>{result.label}</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <div className="flex items-center justify-between border-t px-5 py-3" style={{ borderColor: "hsl(var(--border))" }}>
              <span className="text-xs" style={{ color: "hsl(var(--text-tertiary))" }}>
                第 {currentHistoryPage} / {historyPageCount} 页，共 {loginHistory.length} 条
              </span>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  className="btn-secondary px-3 py-1.5 text-xs"
                  disabled={currentHistoryPage <= 1}
                  onClick={() => setHistoryPage((page) => Math.max(1, page - 1))}
                >
                  上一页
                </button>
                <button
                  type="button"
                  className="btn-secondary px-3 py-1.5 text-xs"
                  disabled={currentHistoryPage >= historyPageCount}
                  onClick={() => setHistoryPage((page) => Math.min(historyPageCount, page + 1))}
                >
                  下一页
                </button>
              </div>
            </div>
          </>
        )}
      </div>

      <Modal open={pwOpen} onClose={() => setPwOpen(false)} title="修改密码" width="md">
        <form onSubmit={handleChangePassword} className="space-y-4">
          {pwError && (
            <div className="flex items-center gap-2 rounded px-3 py-2 text-xs font-medium" style={{ background: "hsl(var(--danger) / 0.08)", color: "hsl(var(--danger))" }}>
              <AlertTriangle size={14} />
              {pwError}
            </div>
          )}
          {pwSuccess && (
            <div className="flex items-center gap-2 rounded px-3 py-2 text-xs font-medium" style={{ background: "hsl(var(--success) / 0.08)", color: "hsl(var(--success))" }}>
              <Check size={14} />
              {pwSuccess}
            </div>
          )}
          <div>
            <label className="mb-1 block text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>当前密码</label>
            <div className="relative">
              <input
                type={showPw ? "text" : "password"}
                className="input pr-9"
                value={oldPw}
                onChange={(e) => setOldPw(e.target.value)}
                required
              />
              <button type="button" className="absolute right-2 top-1/2 -translate-y-1/2" onClick={() => setShowPw(!showPw)} style={{ color: "hsl(var(--text-tertiary))" }}>
                {showPw ? <EyeOff size={14} /> : <Eye size={14} />}
              </button>
            </div>
          </div>
          <div>
            <label className="mb-1 block text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>新密码</label>
            <input
              type={showPw ? "text" : "password"}
              className="input"
              value={newPw}
              onChange={(e) => setNewPw(e.target.value)}
              required
              minLength={minPasswordLength}
            />
            <p className="mt-1 text-[10px]" style={{ color: "hsl(var(--text-tertiary))" }}>至少 {minPasswordLength} 位字符</p>
          </div>
          <div>
            <label className="mb-1 block text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>确认新密码</label>
            <input
              type={showPw ? "text" : "password"}
              className="input"
              value={confirmPw}
              onChange={(e) => setConfirmPw(e.target.value)}
              required
            />
          </div>
          <button type="submit" className="btn-primary w-full" disabled={pwLoading}>
            {pwLoading ? <Loader2 size={14} className="animate-spin" /> : <Lock size={14} />}
            {pwLoading ? "修改中..." : "确认修改"}
          </button>
        </form>
      </Modal>

      <Modal open={totpOpen} onClose={() => setTotpOpen(false)} title="启用两步验证" width="lg">
        {totpLoading && !totpSetup ? (
          <div className="flex items-center justify-center py-10">
            <Loader2 size={24} className="animate-spin" style={{ color: "hsl(var(--text-tertiary))" }} />
          </div>
        ) : recoveryCodes.length > 0 ? (
          <div className="space-y-4">
            <div className="rounded px-3 py-2 text-xs font-medium" style={{ background: "hsl(var(--success) / 0.08)", color: "hsl(var(--success))" }}>
              两步验证已启用
            </div>
            <div className="grid grid-cols-2 gap-2">
              {recoveryCodes.map((code) => (
                <code key={code} className="rounded px-2 py-1 text-center text-xs" style={{ background: "hsl(var(--bg-secondary))", color: "hsl(var(--text-primary))" }}>{code}</code>
              ))}
            </div>
            <button className="btn-primary w-full" onClick={() => setTotpOpen(false)}>完成</button>
          </div>
        ) : (
          <form onSubmit={handleConfirmTotp} className="space-y-4">
            {totpSetup && (
              <>
                <div>
                  <label className="mb-1 block text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>密钥</label>
                  <div className="flex gap-2">
                    <input readOnly className="input flex-1 font-mono text-xs" value={totpSetup.secret} />
                    <button type="button" className="btn-secondary px-3" onClick={() => copyText(totpSetup.secret, () => setCopiedTotp("secret"))}>
                      {copiedTotp === "secret" ? <Check size={14} /> : <Copy size={14} />}
                    </button>
                  </div>
                </div>
                <div>
                  <label className="mb-1 block text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>Authenticator URI</label>
                  <div className="flex gap-2">
                    <input readOnly className="input flex-1 font-mono text-xs" value={totpSetup.uri} />
                    <button type="button" className="btn-secondary px-3" onClick={() => copyText(totpSetup.uri, () => setCopiedTotp("uri"))}>
                      {copiedTotp === "uri" ? <Check size={14} /> : <Copy size={14} />}
                    </button>
                  </div>
                </div>
              </>
            )}
            <div>
              <label className="mb-1 block text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>6 位验证码</label>
              <input
                type="text"
                inputMode="numeric"
                pattern="[0-9]*"
                maxLength={8}
                className="input text-center text-lg tracking-[0.4em]"
                value={totpCode}
                onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, ""))}
                required
              />
            </div>
            {totpError && (
              <div className="rounded px-3 py-2 text-xs font-medium" style={{ background: "hsl(var(--danger) / 0.08)", color: "hsl(var(--danger))" }}>{totpError}</div>
            )}
            <button type="submit" className="btn-primary w-full" disabled={totpLoading || !totpSetup}>
              {totpLoading ? <Loader2 size={14} className="animate-spin" /> : <Shield size={14} />}
              确认启用
            </button>
          </form>
        )}
      </Modal>

      <Modal open={disableTotpOpen} onClose={() => setDisableTotpOpen(false)} title="关闭两步验证" width="md">
        <form onSubmit={handleDisableTotp} className="space-y-4">
          <div className="rounded px-3 py-2 text-xs font-medium" style={{ background: "hsl(var(--warning) / 0.12)", color: "hsl(var(--text-primary))" }}>
            关闭后，后续登录将只验证账号密码。
          </div>
          <div>
            <label className="mb-1 block text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>当前密码</label>
            <input
              type="password"
              className="input"
              value={disableTotpPassword}
              onChange={(e) => setDisableTotpPassword(e.target.value)}
              required
            />
          </div>
          {disableTotpError && (
            <div className="rounded px-3 py-2 text-xs font-medium" style={{ background: "hsl(var(--danger) / 0.08)", color: "hsl(var(--danger))" }}>{disableTotpError}</div>
          )}
          <button type="submit" className="btn-primary w-full" disabled={disableTotpLoading} style={{ background: "hsl(var(--danger))", borderColor: "hsl(var(--danger))" }}>
            {disableTotpLoading ? <Loader2 size={14} className="animate-spin" /> : <AlertTriangle size={14} />}
            确认关闭
          </button>
        </form>
      </Modal>
    </div>
  );
}
