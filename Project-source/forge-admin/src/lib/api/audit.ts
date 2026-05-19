import { apiFetch } from "@/lib/api/client";
import type { AuditLogListResponse } from "@/types/api";

export interface AuditLogQuery {
  actor_id?: string;
  action?: string;
  target_type?: string;
  target_id?: string;
  since?: string;
  until?: string;
  limit?: number;
  offset?: number;
}

function qs(params: Record<string, string | number | undefined>): string {
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== "");
  if (entries.length === 0) return "";
  return "?" + new URLSearchParams(entries.map(([k, v]) => [k, String(v)])).toString();
}

export function listAuditLog(query: AuditLogQuery = {}): Promise<AuditLogListResponse> {
  return apiFetch<AuditLogListResponse>(`/audit${qs(query as Record<string, string | number | undefined>)}`);
}
