"use client";

import { useState, useEffect, useCallback } from "react";
import { Search, Loader2, ClipboardList, Eye, Copy, Check, FileJson, Shield, Link2, Fingerprint, User, LogIn, LogOut, KeyRound, Package, Building2, FileText, Ban } from "lucide-react";
import Modal from "@/components/Modal";
import { api, type AuditEvent } from "@/lib/api";

function formatTime(iso: string) {
  const d = new Date(iso);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}:${String(d.getSeconds()).padStart(2, "0")}`;
}

function truncate(str: string | null, len = 16) {
  if (!str) return "—";
  return str.length > len ? str.slice(0, len) + "…" : str;
}

function formatJson(obj: unknown) {
  return JSON.stringify(obj, null, 2);
}

// ---------- Action mapping ----------

interface ActionMeta {
  label: string;
  badgeClass: string;
  icon: React.ReactNode;
  describe: (e: AuditEvent) => string;
}

function getActionMeta(action: string): ActionMeta {
  const map: Record<string, ActionMeta> = {
    login: {
      label: "登录系统",
      badgeClass: "badge-neutral",
      icon: <LogIn size={12} />,
      describe: (e) => {
        const method = (e.payload.method as string) || "密码";
        return `通过 ${method === "totp" ? "TOTP" : "密码"} 登录系统`;
      },
    },
    logout: {
      label: "退出登录",
      badgeClass: "badge-neutral",
      icon: <LogOut size={12} />,
      describe: () => "退出系统",
    },
    "license.issue": {
      label: "签发 License",
      badgeClass: "badge-info",
      icon: <KeyRound size={12} />,
      describe: (e) => {
        const lid = (e.payload.license_id as string) || "";
        const pcode = (e.payload.product_code as string) || "";
        return `签发了 License「${truncate(lid, 20)}」` + (pcode ? `（产品：${pcode}）` : "");
      },
    },
    "license.renew": {
      label: "续期 License",
      badgeClass: "badge-success",
      icon: <FileText size={12} />,
      describe: (e) => {
        const lid = (e.payload.license_id as string) || "";
        return `续期了 License「${truncate(lid, 20)}」`;
      },
    },
    "license.revoke": {
      label: "吊销 License",
      badgeClass: "badge-danger",
      icon: <Ban size={12} />,
      describe: (e) => {
        const lid = (e.payload.license_id as string) || "";
        return `吊销了 License「${truncate(lid, 20)}」`;
      },
    },
    "customer.create": {
      label: "新增客户",
      badgeClass: "badge-info",
      icon: <Building2 size={12} />,
      describe: (e) => {
        const name = (e.payload.display_name as string) || "";
        return `新增客户「${name}」`;
      },
    },
    "customer.update": {
      label: "编辑客户",
      badgeClass: "badge-success",
      icon: <Building2 size={12} />,
      describe: (e) => {
        const name = (e.payload.display_name as string) || "";
        return `编辑了客户「${name}」`;
      },
    },
    "customer.delete": {
      label: "删除客户",
      badgeClass: "badge-danger",
      icon: <Building2 size={12} />,
      describe: (e) => {
        const name = (e.payload.display_name as string) || "";
        return `删除了客户「${name}」`;
      },
    },
    "product.create": {
      label: "新增产品",
      badgeClass: "badge-info",
      icon: <Package size={12} />,
      describe: (e) => {
        const name = (e.payload.display_name as string) || (e.payload.code as string) || "";
        return `新增产品「${name}」`;
      },
    },
    "product.update": {
      label: "编辑产品",
      badgeClass: "badge-success",
      icon: <Package size={12} />,
      describe: (e) => {
        const name = (e.payload.display_name as string) || (e.payload.code as string) || "";
        return `编辑了产品「${name}」`;
      },
    },
    "product.delete": {
      label: "删除产品",
      badgeClass: "badge-danger",
      icon: <Package size={12} />,
      describe: (e) => {
        const name = (e.payload.display_name as string) || (e.payload.code as string) || "";
        return `删除了产品「${name}」`;
      },
    },
  };
  return (
    map[action] || {
      label: action,
      badgeClass: "badge-neutral",
      icon: <FileText size={12} />,
      describe: () => action,
    }
  );
}

// ---------- Components ----------

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={(e) => {
        e.stopPropagation();
        navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
      className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium transition-colors hover:bg-gray-100"
      style={{ color: "hsl(var(--text-tertiary))" }}
      title="复制"
    >
      {copied ? <Check size={10} /> : <Copy size={10} />}
    </button>
  );
}

function DetailRow({ label, value, mono = false, copyable = false }: { label: string; value: React.ReactNode; mono?: boolean; copyable?: boolean }) {
  const textValue = typeof value === "string" ? value : "";
  return (
    <div className="flex flex-col gap-1 py-2 border-b" style={{ borderColor: "hsl(var(--border))" }}>
      <div className="text-[11px] font-semibold uppercase tracking-wide" style={{ color: "hsl(var(--text-tertiary))" }}>
        {label}
      </div>
      <div className="flex items-start justify-between gap-2">
        <div className={`text-xs break-all ${mono ? "font-mono" : ""}`} style={{ color: "hsl(var(--text-primary))" }}>
          {value}
        </div>
        {copyable && textValue && textValue !== "—" && <CopyButton text={textValue} />}
      </div>
    </div>
  );
}

function AuditDetailModal({ event, open, onClose }: { event: AuditEvent | null; open: boolean; onClose: () => void }) {
  if (!event) return null;
  const meta = getActionMeta(event.action);

  const prevHash = event.prev_hash_hex || "—";
  const hash = event.hash_hex || "—";
  const sig = event.signature_hex || "—";
  const payloadJson = formatJson(event.payload);

  return (
    <Modal open={open} onClose={onClose} title="审计事件详情" width="3xl">
      <div className="space-y-5">
        <div className="surface p-4">
          <div className="mb-3 flex items-center gap-2 text-xs font-bold">
            <FileJson size={14} style={{ color: "hsl(var(--info))" }} />
            基本信息
          </div>
          <div className="grid grid-cols-2 gap-x-6">
            <DetailRow label="事件 ID" value={String(event.id)} />
            <DetailRow label="时间戳" value={formatTime(event.ts)} />
            <DetailRow label="动作代码" value={event.action} />
            <DetailRow label="动作描述" value={meta.label} />
            <DetailRow label="操作者" value={event.actor_name || event.actor_id?.slice(0, 8) || "系统"} />
            <DetailRow label="操作者 ID" value={event.actor_id || "—"} copyable />
            <DetailRow label="操作者 IP" value={event.actor_ip || "—"} />
            <DetailRow label="请求 ID" value={event.request_id || "—"} copyable />
            <DetailRow label="目标类型" value={event.target_kind || "—"} />
            <DetailRow label="目标 ID" value={event.target_id || "—"} copyable />
            <DetailRow label="签名 Key ID" value={event.signature_kid || "—"} copyable />
          </div>
        </div>

        <div className="surface p-4">
          <div className="mb-3 flex items-center gap-2 text-xs font-bold">
            <Link2 size={14} style={{ color: "hsl(var(--info))" }} />
            哈希链（不可篡改）
          </div>
          <div className="space-y-3">
            <div className="rounded-md p-3" style={{ background: "hsl(var(--bg-secondary))" }}>
              <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide" style={{ color: "hsl(var(--text-tertiary))" }}>上一块哈希 (prev_hash)</div>
              <div className="flex items-start justify-between gap-2">
                <code className="break-all font-mono text-[11px] leading-relaxed" style={{ color: "hsl(var(--text-secondary))" }}>{prevHash}</code>
                {prevHash !== "—" && <CopyButton text={prevHash} />}
              </div>
            </div>
            <div className="flex justify-center"><div className="h-4 w-px" style={{ background: "hsl(var(--border))" }} /></div>
            <div className="rounded-md p-3" style={{ background: "hsl(var(--bg-secondary))" }}>
              <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide" style={{ color: "hsl(var(--text-tertiary))" }}>当前哈希 (hash)</div>
              <div className="flex items-start justify-between gap-2">
                <code className="break-all font-mono text-[11px] leading-relaxed" style={{ color: "hsl(var(--text-primary))" }}>{hash}</code>
                {hash !== "—" && <CopyButton text={hash} />}
              </div>
            </div>
          </div>
        </div>

        <div className="surface p-4">
          <div className="mb-3 flex items-center gap-2 text-xs font-bold">
            <Shield size={14} style={{ color: "hsl(var(--success))" }} />
            数字签名
          </div>
          <div className="rounded-md p-3" style={{ background: "hsl(var(--bg-secondary))" }}>
            <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide" style={{ color: "hsl(var(--text-tertiary))" }}>Ed25519 签名值 (hex)</div>
            <div className="flex items-start justify-between gap-2">
              <code className="break-all font-mono text-[11px] leading-relaxed" style={{ color: "hsl(var(--text-primary))" }}>{sig}</code>
              {sig !== "—" && <CopyButton text={sig} />}
            </div>
          </div>
        </div>

        <div className="surface p-4">
          <div className="mb-3 flex items-center gap-2 text-xs font-bold">
            <Fingerprint size={14} style={{ color: "hsl(var(--warning))" }} />
            操作载荷 (Payload)
          </div>
          <div className="relative rounded-md p-3" style={{ background: "hsl(var(--bg-secondary))" }}>
            <div className="absolute right-2 top-2"><CopyButton text={payloadJson} /></div>
            <pre className="overflow-auto font-mono text-[11px] leading-relaxed" style={{ color: "hsl(var(--text-secondary))", maxHeight: "240px" }}>
              {payloadJson}
            </pre>
          </div>
        </div>
      </div>
    </Modal>
  );
}

// ---------- Page ----------

export default function AuditPage() {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [selectedEvent, setSelectedEvent] = useState<AuditEvent | null>(null);

  const fetchEvents = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await api.list<AuditEvent>("/audit/");
      setEvents(data);
    } catch (e: any) {
      setError(e.detail || "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchEvents();
  }, [fetchEvents]);

  const filtered = events.filter((e) => {
    if (!search) return true;
    const s = search.toLowerCase();
    const meta = getActionMeta(e.action);
    return (
      (e.actor_name || "").toLowerCase().includes(s) ||
      (e.actor_id || "").toLowerCase().includes(s) ||
      e.action.toLowerCase().includes(s) ||
      meta.label.toLowerCase().includes(s) ||
      meta.describe(e).toLowerCase().includes(s) ||
      (e.target_kind || "").toLowerCase().includes(s) ||
      (e.target_id || "").toLowerCase().includes(s) ||
      (e.actor_ip || "").toLowerCase().includes(s)
    );
  });

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold" style={{ color: "hsl(var(--text-primary))" }}>审计日志</h1>
          <p className="mt-0.5 text-xs font-medium" style={{ color: "hsl(var(--text-secondary))" }}>
            记录谁在什么时间做了什么事
          </p>
        </div>
      </div>

      {/* Toolbar */}
      <div className="surface flex items-center gap-3 p-3">
        <div className="relative flex-1 max-w-md">
          <Search size={16} className="absolute left-2.5 top-1/2 -translate-y-1/2" style={{ color: "hsl(var(--text-tertiary))" }} />
          <input
            type="text"
            className="input pl-9"
            placeholder="搜索操作人、动作、目标..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div className="ml-auto text-xs" style={{ color: "hsl(var(--text-tertiary))" }}>
          共 {filtered.length} 条记录
        </div>
      </div>

      {error && (
        <div className="surface px-4 py-3 text-xs font-medium" style={{ color: "hsl(var(--danger))" }}>
          {error}
        </div>
      )}

      <div className="surface overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 size={24} className="animate-spin" style={{ color: "hsl(var(--text-tertiary))" }} />
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr style={{ background: "hsl(var(--bg-secondary))" }}>
                <th className="px-4 py-3 text-left text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>时间</th>
                <th className="px-4 py-3 text-left text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>操作人</th>
                <th className="px-4 py-3 text-left text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>操作</th>
                <th className="px-4 py-3 text-left text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>目标</th>
                <th className="px-4 py-3 text-right text-xs font-semibold" style={{ color: "hsl(var(--text-secondary))" }}></th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-4 py-16 text-center">
                    <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full" style={{ background: "hsl(var(--bg-tertiary))" }}>
                      <ClipboardList size={20} style={{ color: "hsl(var(--text-tertiary))" }} />
                    </div>
                    <div className="text-sm font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>暂无审计记录</div>
                    <div className="mt-1 text-xs" style={{ color: "hsl(var(--text-tertiary))" }}>操作日志将在登录、签发、续期、吊销、客户/产品变更时自动记录</div>
                  </td>
                </tr>
              ) : (
                filtered.map((e) => {
                  const meta = getActionMeta(e.action);
                  return (
                    <tr
                      key={e.id}
                      className="border-t cursor-pointer transition-colors hover:bg-gray-50"
                      style={{ borderColor: "hsl(var(--border))" }}
                      onClick={() => setSelectedEvent(e)}
                    >
                      <td className="px-4 py-3 text-xs font-mono whitespace-nowrap" style={{ color: "hsl(var(--text-secondary))" }}>{formatTime(e.ts)}</td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <div className="flex h-6 w-6 items-center justify-center rounded-full text-[10px] font-bold" style={{ background: "hsl(var(--bg-tertiary))", color: "hsl(var(--text-secondary))" }}>
                            <User size={12} />
                          </div>
                          <div className="flex flex-col">
                            <span className="text-xs font-medium" style={{ color: "hsl(var(--text-primary))" }}>{e.actor_name || "系统"}</span>
                            {e.actor_id && (
                              <span className="text-[10px] font-mono" style={{ color: "hsl(var(--text-tertiary))" }}>ID: {truncate(e.actor_id, 12)}</span>
                            )}
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <span className={`inline-flex items-center gap-1 badge ${meta.badgeClass} text-[10px]`}>
                            {meta.icon}
                            {meta.label}
                          </span>
                          <span className="text-xs" style={{ color: "hsl(var(--text-secondary))" }}>{meta.describe(e)}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-xs" style={{ color: "hsl(var(--text-secondary))" }}>
                        {e.target_kind ? (
                          <span className="font-mono">
                            {e.target_kind}:{truncate(e.target_id, 12)}
                          </span>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button
                          className="inline-flex items-center gap-1 rounded p-1.5 text-[10px] font-medium transition-colors hover:bg-gray-100"
                          style={{ color: "hsl(var(--text-tertiary))" }}
                          onClick={(ev) => {
                            ev.stopPropagation();
                            setSelectedEvent(e);
                          }}
                        >
                          <Eye size={12} />
                          详情
                        </button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        )}
      </div>

      <AuditDetailModal
        event={selectedEvent}
        open={!!selectedEvent}
        onClose={() => setSelectedEvent(null)}
      />
    </div>
  );
}
