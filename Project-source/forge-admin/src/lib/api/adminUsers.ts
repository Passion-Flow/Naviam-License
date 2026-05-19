import { apiFetch } from "@/lib/api/client";
import type {
  AdminUserEntry,
  AdminUserListResponse,
  CreateAdminUserBody,
  ResetAdminPasswordBody,
} from "@/types/api";

export function listAdminUsers(): Promise<AdminUserListResponse> {
  return apiFetch<AdminUserListResponse>("/admin/users");
}

export function createAdminUser(body: CreateAdminUserBody): Promise<AdminUserEntry> {
  return apiFetch<AdminUserEntry>("/admin/users", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function deactivateAdminUser(id: string): Promise<AdminUserEntry> {
  return apiFetch<AdminUserEntry>(`/admin/users/${encodeURIComponent(id)}/deactivate`, {
    method: "POST",
  });
}

export function reactivateAdminUser(id: string): Promise<AdminUserEntry> {
  return apiFetch<AdminUserEntry>(`/admin/users/${encodeURIComponent(id)}/reactivate`, {
    method: "POST",
  });
}

export function resetAdminUserPassword(
  id: string,
  body: ResetAdminPasswordBody,
): Promise<AdminUserEntry> {
  return apiFetch<AdminUserEntry>(`/admin/users/${encodeURIComponent(id)}/reset-password`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/** Hard delete — drops the admin user row. Audit log entries stay intact (append-only). */
export function hardDeleteAdminUser(id: string): Promise<{ user_id: string; deleted: boolean }> {
  return apiFetch(`/admin/users/${encodeURIComponent(id)}`, { method: "DELETE" });
}
