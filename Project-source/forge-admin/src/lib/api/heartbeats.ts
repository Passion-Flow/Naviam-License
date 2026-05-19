import { apiFetch } from "@/lib/api/client";
import type {
  HeartbeatListResponse,
  HeartbeatSummaryResponse,
  LicenseHeartbeatDetail,
} from "@/types/api";

export interface HeartbeatListQuery {
  license_id?: string;
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

export function listHeartbeats(query: HeartbeatListQuery = {}): Promise<HeartbeatListResponse> {
  return apiFetch<HeartbeatListResponse>(`/heartbeats${qs(query as Record<string, string | number | undefined>)}`);
}

export function getHeartbeatSummary(sinceSeconds = 86_400, limit = 200): Promise<HeartbeatSummaryResponse> {
  return apiFetch<HeartbeatSummaryResponse>(
    `/heartbeats/summary?since_seconds=${sinceSeconds}&limit=${limit}`,
  );
}

export function getHeartbeatDetail(
  licenseId: string,
  sinceSeconds = 86_400,
  limit = 100,
): Promise<LicenseHeartbeatDetail> {
  return apiFetch<LicenseHeartbeatDetail>(
    `/heartbeats/${encodeURIComponent(licenseId)}?since_seconds=${sinceSeconds}&limit=${limit}`,
  );
}
