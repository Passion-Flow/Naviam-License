import { apiFetch } from "@/lib/api/client";

export interface SessionEntry {
  sid_prefix: string;
  created_at: string;
  expires_at: string;
  is_current: boolean;
}

export interface SessionListResponse {
  items: SessionEntry[];
}

export function listMySessions(): Promise<SessionListResponse> {
  return apiFetch<SessionListResponse>("/auth/sessions");
}

export function revokeSession(sidPrefix: string): Promise<void> {
  return apiFetch<void>(`/auth/sessions/${encodeURIComponent(sidPrefix)}`, {
    method: "DELETE",
  });
}
