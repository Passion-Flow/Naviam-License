"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState, useEffect } from "react";
import {
  KeyRound,
  Users,
  Package,
  ClipboardList,
  Bell,
  Settings,
  Shield,
  LogOut,
} from "lucide-react";
import { api } from "@/lib/api";

const NAV = [
  { href: "/licenses", label: "License", icon: KeyRound },
  { href: "/customers", label: "客户", icon: Users },
  { href: "/products", label: "产品", icon: Package },
  { href: "/audit", label: "审计", icon: ClipboardList },
  { href: "/notifications", label: "通知", icon: Bell },
  { href: "/settings", label: "设置", icon: Settings },
];

function NavItem({ href, label, icon: Icon, badge }: { href: string; label: string; icon: React.ElementType; badge?: number }) {
  const pathname = usePathname();
  const active = pathname === href || pathname.startsWith(`${href}/`);
  return (
    <Link href={href} className="nav-link" data-active={active}>
      <Icon size={18} strokeWidth={active ? 2.2 : 1.8} />
      <span>{label}</span>
      {badge ? (
        <span className="ml-auto flex h-4 min-w-4 items-center justify-center rounded-full px-1 text-[10px] font-bold text-white" style={{ background: "hsl(var(--danger))" }}>
          {badge > 99 ? "99+" : badge}
        </span>
      ) : null}
    </Link>
  );
}

function LogoutButton() {
  const router = useRouter();
  async function handleLogout() {
    try {
      await api.post("/auth/logout/", {});
    } catch {
      // ignore
    }
    router.push("/login");
  }
  return (
    <button className="nav-link w-full" style={{ color: "hsl(var(--text-tertiary))" }} onClick={handleLogout}>
      <LogOut size={18} strokeWidth={1.8} />
      <span>退出登录</span>
    </button>
  );
}

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const [unreadCount, setUnreadCount] = useState(0);

  useEffect(() => {
    let mounted = true;
    async function fetchUnread() {
      try {
        const data = await api.get<{ unread_count: number }>("/notifications/unread-count/");
        if (mounted) setUnreadCount(data.unread_count);
      } catch {
        // ignore
      }
    }
    fetchUnread();
    const id = setInterval(fetchUnread, 30000);

    function onUpdate() {
      fetchUnread();
    }
    window.addEventListener("notifications-updated", onUpdate);

    return () => {
      mounted = false;
      clearInterval(id);
      window.removeEventListener("notifications-updated", onUpdate);
    };
  }, []);

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <aside className="flex h-screen w-60 shrink-0 flex-col border-r" style={{ background: "hsl(var(--bg-primary))" }}>
        {/* Brand */}
        <div className="flex items-center gap-2.5 px-4 py-5">
          <div
            className="flex h-8 w-8 items-center justify-center rounded-md"
            style={{ background: "hsl(var(--brand-600))" }}
          >
            <Shield size={16} color="white" strokeWidth={2.5} />
          </div>
          <div>
            <div className="text-sm font-bold leading-tight" style={{ color: "hsl(var(--text-primary))" }}>
              License Console
            </div>
            <div className="text-[11px] font-medium leading-tight" style={{ color: "hsl(var(--text-tertiary))" }}>
              厂商签发台
            </div>
          </div>
        </div>

        {/* Nav */}
        <nav className="min-h-0 flex-1 space-y-0.5 overflow-y-auto px-3 py-2">
          {NAV.map((item) => (
            <NavItem
              key={item.href}
              {...item}
              badge={item.href === "/notifications" ? unreadCount : undefined}
            />
          ))}
        </nav>

        {/* Bottom */}
        <div className="border-t px-3 py-3">
          <LogoutButton />
        </div>
      </aside>

      {/* Main */}
      <main className="h-screen min-w-0 flex-1 overflow-y-auto" style={{ background: "hsl(var(--bg-secondary))" }}>
        {children}
      </main>
    </div>
  );
}
