"use client";

import { useState, useEffect, useCallback } from "react";
import { Bell, Check, Trash2, Loader2, CheckCheck, Info, Shield, FileText, Building2 } from "lucide-react";
import { api, type Notification } from "@/lib/api";

function formatTime(iso: string) {
  const d = new Date(iso);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")} ${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

type CategoryMeta = { label: string; icon: React.ReactNode; color: string; bg: string };

const DEFAULT_CATEGORY_META: CategoryMeta = {
  label: "System",
  icon: <Info size={14} />,
  color: "hsl(var(--brand-600))",
  bg: "hsl(var(--brand-50))",
};

const CATEGORY_META: Record<string, CategoryMeta> = {
  license: { label: "License", icon: <FileText size={14} />, color: "hsl(var(--info))", bg: "hsl(var(--info) / 0.08)" },
  customer: { label: "客户", icon: <Building2 size={14} />, color: "hsl(var(--success))", bg: "hsl(var(--success) / 0.08)" },
  product: { label: "产品", icon: <FileText size={14} />, color: "hsl(var(--warning))", bg: "hsl(var(--warning) / 0.08)" },
  system: { label: "系统", icon: <Info size={14} />, color: "hsl(var(--brand-600))", bg: "hsl(var(--brand-50))" },
  security: { label: "安全", icon: <Shield size={14} />, color: "hsl(var(--danger))", bg: "hsl(var(--danger) / 0.08)" },
};

export default function NotificationsPage() {
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState<"all" | "unread">("all");
  const [unreadCount, setUnreadCount] = useState(0);
  const [totalCount, setTotalCount] = useState(0);

  const fetchNotifications = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await api.list<Notification>(`/notifications/${filter === "unread" ? "?unread_only=true" : ""}`);
      setNotifications(data);
      if (filter === "all") {
        setTotalCount(data.length);
      }
    } catch (e: any) {
      setError(e.detail || "加载失败");
    } finally {
      setLoading(false);
    }
  }, [filter]);

  const fetchCounts = useCallback(async () => {
    try {
      const unreadData = await api.get<{ unread_count: number }>("/notifications/unread-count/");
      setUnreadCount(unreadData.unread_count);
      // Also fetch total count
      const allData = await api.list<Notification>("/notifications/");
      setTotalCount(allData.length);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    fetchNotifications();
    fetchCounts();
  }, [fetchNotifications, fetchCounts]);

  const handleMarkRead = async (id: string) => {
    setError("");
    try {
      await api.post(`/notifications/${id}/read/`, {});
      if (filter === "unread") {
        // Remove from list immediately when in unread filter
        setNotifications((prev) => prev.filter((n) => n.id !== id));
      } else {
        setNotifications((prev) =>
          prev.map((n) => (n.id === id ? { ...n, is_read: true } : n))
        );
      }
      setUnreadCount((c) => Math.max(0, c - 1));
      window.dispatchEvent(new CustomEvent("notifications-updated"));
    } catch (e: any) {
      setError(e.detail || "操作失败");
    }
  };

  const handleMarkAllRead = async () => {
    setError("");
    try {
      await api.post("/notifications/mark-all-read/", {});
      if (filter === "unread") {
        setNotifications([]);
      } else {
        setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
      }
      setUnreadCount(0);
      window.dispatchEvent(new CustomEvent("notifications-updated"));
    } catch (e: any) {
      setError(e.detail || "操作失败");
    }
  };

  const handleDelete = async (id: string) => {
    setError("");
    try {
      const wasUnread = notifications.find((n) => n.id === id)?.is_read === false;
      await api.delete(`/notifications/${id}/`);
      setNotifications((prev) => prev.filter((n) => n.id !== id));
      setTotalCount((c) => Math.max(0, c - 1));
      if (wasUnread) {
        setUnreadCount((c) => Math.max(0, c - 1));
      }
      window.dispatchEvent(new CustomEvent("notifications-updated"));
    } catch (e: any) {
      setError(e.detail || "删除失败");
    }
  };

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold" style={{ color: "hsl(var(--text-primary))" }}>
            通知中心
          </h1>
          <p className="mt-0.5 text-xs font-medium" style={{ color: "hsl(var(--text-secondary))" }}>
            系统通知与安全提醒
          </p>
        </div>
        <div className="flex items-center gap-2">
          {unreadCount > 0 && (
            <button className="btn-secondary text-xs" onClick={handleMarkAllRead}>
              <CheckCheck size={14} />
              全部已读
            </button>
          )}
        </div>
      </div>

      {/* Filter tabs */}
      <div className="flex items-center gap-1">
        <button
          className={`rounded px-3 py-1.5 text-xs font-medium transition-colors ${filter === "all" ? "text-white" : ""}`}
          style={filter === "all" ? { background: "hsl(var(--brand-600))" } : { color: "hsl(var(--text-secondary))" }}
          onClick={() => setFilter("all")}
        >
          全部 {totalCount > 0 && `(${totalCount})`}
        </button>
        <button
          className={`rounded px-3 py-1.5 text-xs font-medium transition-colors ${filter === "unread" ? "text-white" : ""}`}
          style={filter === "unread" ? { background: "hsl(var(--brand-600))" } : { color: "hsl(var(--text-secondary))" }}
          onClick={() => setFilter("unread")}
        >
          未读 {unreadCount > 0 && `(${unreadCount})`}
        </button>
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
        ) : notifications.length === 0 ? (
          <div className="px-4 py-16 text-center">
            <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full" style={{ background: "hsl(var(--bg-tertiary))" }}>
              <Bell size={20} style={{ color: "hsl(var(--text-tertiary))" }} />
            </div>
            <div className="text-sm font-semibold" style={{ color: "hsl(var(--text-secondary))" }}>暂无通知</div>
            <div className="mt-1 text-xs" style={{ color: "hsl(var(--text-tertiary))" }}>
              {filter === "unread" ? "所有通知已读" : "当系统有重要事件时会自动推送通知"}
            </div>
          </div>
        ) : (
          <div className="divide-y" style={{ borderColor: "hsl(var(--border))" }}>
            {notifications.map((n) => {
              const meta = CATEGORY_META[n.category] ?? DEFAULT_CATEGORY_META;
              return (
                <div
                  key={n.id}
                  className={`flex items-start gap-3 px-4 py-4 transition-colors ${!n.is_read ? "bg-blue-50/30" : ""} hover:bg-gray-50`}
                >
                  <div
                    className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg"
                    style={{ background: meta.bg, color: meta.color }}
                  >
                    {meta.icon}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-semibold" style={{ color: "hsl(var(--text-primary))" }}>
                        {n.title}
                      </span>
                      {!n.is_read && (
                        <span className="h-1.5 w-1.5 rounded-full" style={{ background: "hsl(var(--danger))" }} />
                      )}
                      <span className="ml-auto text-[10px] font-mono" style={{ color: "hsl(var(--text-tertiary))" }}>
                        {formatTime(n.created_at)}
                      </span>
                    </div>
                    <p className="mt-1 text-xs" style={{ color: "hsl(var(--text-secondary))" }}>
                      {n.message}
                    </p>
                    <div className="mt-2 flex items-center gap-2">
                      <span
                        className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium"
                        style={{ background: meta.bg, color: meta.color }}
                      >
                        {meta.label}
                      </span>
                    </div>
                  </div>
                  <div className="flex shrink-0 flex-col gap-1">
                    {!n.is_read && (
                      <button
                        className="rounded p-1.5 transition-colors hover:bg-gray-100"
                        style={{ color: "hsl(var(--text-tertiary))" }}
                        onClick={() => handleMarkRead(n.id)}
                        title="标记已读"
                      >
                        <Check size={14} />
                      </button>
                    )}
                    <button
                      className="rounded p-1.5 transition-colors hover:bg-gray-100"
                      style={{ color: "hsl(var(--danger))" }}
                      onClick={() => handleDelete(n.id)}
                      title="删除"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
