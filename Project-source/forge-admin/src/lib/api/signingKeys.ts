import { apiFetch } from "@/lib/api/client";
import type {
  GenerateSigningKeyBody,
  RotateSigningKeyResponse,
  SigningKeyListResponse,
  SigningKeyResponse,
} from "@/types/api";

export interface SigningKeyListQuery {
  algorithm?: string;
  status?: string;
}

function qs(params: Record<string, string | number | undefined>): string {
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== "");
  if (entries.length === 0) return "";
  return "?" + new URLSearchParams(entries.map(([k, v]) => [k, String(v)])).toString();
}

export function listSigningKeys(query: SigningKeyListQuery = {}): Promise<SigningKeyListResponse> {
  return apiFetch<SigningKeyListResponse>(`/keys${qs(query as Record<string, string | number | undefined>)}`);
}

export function generateSigningKey(body: GenerateSigningKeyBody): Promise<SigningKeyResponse> {
  return apiFetch<SigningKeyResponse>("/keys/generate", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function rotateSigningKey(keyId: string): Promise<RotateSigningKeyResponse> {
  return apiFetch<RotateSigningKeyResponse>(`/keys/${encodeURIComponent(keyId)}/rotate`, {
    method: "POST",
  });
}

export function revokeSigningKey(keyId: string, reason: string): Promise<SigningKeyResponse> {
  return apiFetch<SigningKeyResponse>(`/keys/${encodeURIComponent(keyId)}/revoke`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

export function exportPublicKey(keyId: string): Promise<SigningKeyResponse> {
  return apiFetch<SigningKeyResponse>(`/keys/${encodeURIComponent(keyId)}/export-public`);
}

/** Hard delete — drops the signing-key row + cascades to ALL licenses signed by it. */
export function hardDeleteSigningKey(keyId: string): Promise<{ key_id: string; cascaded: Record<string, number> }> {
  return apiFetch(`/keys/${encodeURIComponent(keyId)}`, { method: "DELETE" });
}
