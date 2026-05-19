import { apiFetch, resolveConfig } from "@/lib/api/client";
import type {
  IssueLicenseBody,
  IssueLicenseResponse,
  LicenseDetail,
  LicenseListResponse,
  RenewLicenseBody,
  RenewLicenseResponse,
  RevokeLicenseResponse,
} from "@/types/api";

export interface LicenseListQuery {
  customer_id?: string;
  product_id?: string;
  mode?: string;
  algorithm?: string;
  q?: string; // license_id substring (server: ILIKE)
  limit?: number;
  offset?: number;
}

export interface BulkRevokeBody {
  license_ids: string[];
  reason?: string;
}

export interface BulkRevokeItem {
  license_id: string;
  status: "revoked" | "not_found" | "already_revoked";
}

export interface BulkRevokeResponse {
  items: BulkRevokeItem[];
  revoked_count: number;
  not_found_count: number;
  already_revoked_count: number;
}

function qs(params: Record<string, string | number | undefined>): string {
  const entries = Object.entries(params).filter(([, v]) => v !== undefined && v !== "");
  if (entries.length === 0) return "";
  return "?" + new URLSearchParams(entries.map(([k, v]) => [k, String(v)])).toString();
}

export function listLicenses(query: LicenseListQuery = {}): Promise<LicenseListResponse> {
  return apiFetch<LicenseListResponse>(`/licenses${qs(query as Record<string, string | number | undefined>)}`);
}

export function getLicense(id: string): Promise<LicenseDetail> {
  return apiFetch<LicenseDetail>(`/licenses/${encodeURIComponent(id)}`);
}

export function issueLicense(body: IssueLicenseBody): Promise<IssueLicenseResponse> {
  return apiFetch<IssueLicenseResponse>("/licenses/issue", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function revokeLicense(
  id: string,
  reason: string,
): Promise<RevokeLicenseResponse> {
  return apiFetch<RevokeLicenseResponse>(
    `/licenses/${encodeURIComponent(id)}/revoke`,
    { method: "POST", body: JSON.stringify({ reason }) },
  );
}

export function unrevokeLicense(id: string): Promise<{ license_id: string; revoked: boolean }> {
  return apiFetch<{ license_id: string; revoked: boolean }>(
    `/licenses/${encodeURIComponent(id)}/unrevoke`,
    { method: "POST" },
  );
}

export function renewLicense(id: string, body: RenewLicenseBody): Promise<RenewLicenseResponse> {
  return apiFetch<RenewLicenseResponse>(`/licenses/${encodeURIComponent(id)}/renew`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export interface VerifyLicenseBody {
  forge_file_b64: string;
  deployment_fingerprint?: string;
}

export interface VerifyLicenseResponse {
  status:
    | "valid"
    | "expired"
    | "revoked"
    | "binding_mismatch"
    | "signature_invalid"
    | "unknown_key"
    | "malformed";
  license_id: string | null;
  valid_until: string | null;
  reason: string | null;
  server_time: string;
}

export function verifyLicense(body: VerifyLicenseBody): Promise<VerifyLicenseResponse> {
  return apiFetch<VerifyLicenseResponse>("/licenses/verify", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function bulkRevokeLicenses(body: BulkRevokeBody): Promise<BulkRevokeResponse> {
  return apiFetch<BulkRevokeResponse>("/licenses/bulk-revoke", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

/**
 * .forge 文件直接拉二进制；走 fetch 不经 apiFetch，以保持 Blob body。
 */
export async function downloadLicense(id: string): Promise<Blob> {
  const base = resolveConfig().apiBaseUrl;
  const res = await fetch(`${base}/licenses/${encodeURIComponent(id)}/download`, {
    credentials: "include",
  });
  if (!res.ok) {
    throw new Error(`download failed: ${res.status}`);
  }
  return res.blob();
}

/** Hard delete — drops the license row and cascades to its heartbeats / nonces / revocations. */
export function hardDeleteLicense(licenseId: string): Promise<{ license_id: string; cascaded: Record<string, number> }> {
  return apiFetch(`/licenses/${encodeURIComponent(licenseId)}`, { method: "DELETE" });
}
