import { apiFetch } from "@/lib/api/client";
import type {
  ApiKeyListResponse,
  IssueApiKeyBody,
  IssueApiKeyResponse,
  RevokeApiKeyResponse,
} from "@/types/api";

export interface ApiKeyListQuery {
  status?: "active" | "revoked";
  customer_id?: string;
  limit?: number;
  offset?: number;
}

function qs(params: Record<string, string | number | undefined>): string {
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== "");
  if (entries.length === 0) return "";
  return "?" + new URLSearchParams(entries.map(([k, v]) => [k, String(v)])).toString();
}

export function listApiKeys(query: ApiKeyListQuery = {}): Promise<ApiKeyListResponse> {
  return apiFetch<ApiKeyListResponse>(`/api-keys${qs(query as Record<string, string | number | undefined>)}`);
}

export function issueApiKey(body: IssueApiKeyBody): Promise<IssueApiKeyResponse> {
  return apiFetch<IssueApiKeyResponse>("/api-keys", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function revokeApiKey(keyId: string): Promise<RevokeApiKeyResponse> {
  return apiFetch<RevokeApiKeyResponse>(`/api-keys/${encodeURIComponent(keyId)}/revoke`, {
    method: "POST",
  });
}

/** Hard delete — drops the api_key row; nullifies api_key_id on heartbeat logs. */
export function hardDeleteApiKey(keyId: string): Promise<{ key_id: string; deleted: boolean }> {
  return apiFetch(`/api-keys/${encodeURIComponent(keyId)}`, { method: "DELETE" });
}
