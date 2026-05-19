/**
 * 后端 Pydantic 响应类型 —— 与 forge-server/app/api/v1 一一对应。
 * 字段名严格保持后端 snake_case，不在前端转 camelCase（避免双向 mapping 漂移）。
 */

export interface AdminUser {
  user_id: string;
  username: string;
  is_super: boolean;
  // 本次 session 用文档化默认密码 (`bootstrap_admin_password`) 登录时为 true。
  // 改密后 session 被销毁，下次登录就归 false。前端据此挂横幅催改。
  is_default_password: boolean;
}

// ─── Admin team management (super-only mutations) ───────────────

export interface AdminUserEntry {
  id: string;
  username: string;
  email: string;
  is_super: boolean;
  is_active: boolean;
  last_login_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AdminUserListResponse {
  items: AdminUserEntry[];
}

export interface CreateAdminUserBody {
  username: string;
  email: string;
  password: string;
  is_super?: boolean;
}

export interface ResetAdminPasswordBody {
  new_password: string;
}

export interface CustomerResponse {
  id: string;
  slug: string;
  name: string;
  contact_email: string;
  contact_name: string;
  region: string;
  status: "active" | "archived";
  notes: string;
  created_at: string;
  updated_at: string;
}

export interface CustomerListResponse {
  items: CustomerResponse[];
  limit: number;
  offset: number;
}

export interface CreateCustomerBody {
  slug: string;
  name: string;
  contact_email?: string;
  contact_name?: string;
  region?: string;
  notes?: string;
}

export interface UpdateCustomerBody {
  name?: string;
  contact_email?: string;
  contact_name?: string;
  region?: string;
  notes?: string;
  status?: "active" | "archived";
}

// ─── Licenses ────────────────────────────────────────────────────

export type VerificationMode = "offline" | "hybrid" | "online";
export type LicenseScope = "customer_x_product" | "customer_bundle" | "instance";
export type SigningAlgorithm = "ed25519" | "rsa2048" | "rsa4096" | "sm2";
export type BindingMode = "none" | "soft" | "hard";

export interface LicenseSummary {
  license_id: string;
  customer_id: string;
  product_id: string;
  mode: VerificationMode;
  scope: LicenseScope;
  algorithm: SigningAlgorithm;
  binding: BindingMode;
  signing_key_id: string;
  issued_at: string;
  expires_at: string;
  is_revoked: boolean;
}

export interface LicenseListResponse {
  items: LicenseSummary[];
  limit: number;
  offset: number;
}

export interface LicenseDetail extends LicenseSummary {
  bound_fingerprint: string | null;
  features: Record<string, unknown>;
  limits: Record<string, unknown>;
  notes: string;
  revoked: boolean;
}

export interface IssueLicenseBody {
  customer_id: string;
  product_id: string;
  mode: VerificationMode;
  scope: LicenseScope;
  algorithm: SigningAlgorithm;
  binding: BindingMode;
  expires_at: string; // ISO 8601
  features?: Record<string, unknown>;
  limits?: Record<string, unknown>;
  bound_fingerprint?: string;
  key_id?: string;
}

export interface IssueLicenseResponse {
  license_id: string;
  forge_file_b64: string;
  signing_key_id: string;
  algorithm: SigningAlgorithm;
  issued_by: string;
}

export interface RevokeLicenseResponse {
  license_id: string;
  revoked: boolean;
  revoked_at: string;
  reason: string;
  revoked_by: string;
}

export interface RenewLicenseBody {
  expires_at: string;
  features?: Record<string, unknown>;
  limits?: Record<string, unknown>;
  revoke_old?: boolean;
  reason?: string;
}

export interface RenewLicenseResponse {
  old_license_id: string;
  new_license_id: string;
  forge_file_b64: string;
  signing_key_id: string;
  algorithm: SigningAlgorithm;
  issued_by: string;
  old_revoked: boolean;
}

// ─── API Keys (verifier-side credentials) ────────────────────────

export type ApiKeyStatus = "active" | "revoked";

export interface ApiKeyEntry {
  key_id: string;
  key_prefix: string;
  customer_id: string;
  project_label: string;
  status: ApiKeyStatus;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
  // null = 永不过期；非 null 时鉴权时点比当前时间晚才视为有效。
  expires_at: string | null;
}

export interface ApiKeyListResponse {
  items: ApiKeyEntry[];
  limit: number;
  offset: number;
}

export interface IssueApiKeyBody {
  customer_id: string;
  project_label: string;
  // 可选 TTL：从 now 起的天数。后端上限 10 年；不传 = 永不过期。
  expires_in_days?: number;
}

export interface IssueApiKeyResponse extends ApiKeyEntry {
  plaintext: string; // 仅一次返回
}

export interface RevokeApiKeyResponse {
  key_id: string;
  status: ApiKeyStatus;
}

// ─── Signing Keys ────────────────────────────────────────────────

export type SigningKeyStatus = "active" | "rotated" | "revoked";

export interface SigningKeyResponse {
  key_id: string;
  algorithm: SigningAlgorithm;
  status: SigningKeyStatus;
  created_at: string;
  activated_at: string | null;
  rotated_at: string | null;
  revoked_at: string | null;
  public_key_b64: string;
}

export interface SigningKeyListResponse {
  items: SigningKeyResponse[];
}

export interface GenerateSigningKeyBody {
  algorithm: SigningAlgorithm;
  activate?: boolean;
}

export interface RotateSigningKeyResponse {
  old_key_id: string;
  old_status: SigningKeyStatus;
  new_key: SigningKeyResponse;
}

// ─── Products ────────────────────────────────────────────────────

export interface ProductResponse {
  id: string;
  slug: string;
  name: string;
  description: string;
  version: string;
  features_schema: Record<string, unknown>;
  default_limits: Record<string, unknown>;
  status: "active" | "archived";
  created_at: string;
  updated_at: string;
}

export interface ProductListResponse {
  items: ProductResponse[];
  limit: number;
  offset: number;
}

export interface CreateProductBody {
  slug: string;
  name: string;
  description?: string;
  version?: string;
  features_schema?: Record<string, unknown>;
  default_limits?: Record<string, unknown>;
}

export interface UpdateProductBody {
  name?: string;
  description?: string;
  version?: string;
  features_schema?: Record<string, unknown>;
  default_limits?: Record<string, unknown>;
  status?: "active" | "archived";
}

// ─── Heartbeats ──────────────────────────────────────────────────

export interface HeartbeatEntry {
  id: number;
  license_id: string;
  fingerprint: string;
  received_at: string;
  reported_at: string;
  nonce: string;
  api_key_id: string | null;
  verifier_version: string;
}

export interface HeartbeatListResponse {
  items: HeartbeatEntry[];
  limit: number;
  offset: number;
}

export interface HeartbeatSummaryItem {
  license_id: string;
  total_count: number;
  distinct_fingerprint_count: number;
  last_seen_at: string;
  last_fingerprint: string;
  anomaly: boolean;
  anomaly_reason: string | null;
  threshold: number;
  window_seconds: number;
}

export interface HeartbeatSummaryResponse {
  items: HeartbeatSummaryItem[];
}

export interface FingerprintSeen {
  fingerprint: string;
  first_seen_at: string;
}

export interface HeartbeatDetectorVerdict {
  anomaly: boolean;
  distinct_fingerprint_count: number;
  threshold: number;
  window_seconds: number;
  reason: string | null;
}

export interface LicenseHeartbeatDetail {
  license_id: string;
  recent_heartbeats: HeartbeatEntry[];
  fingerprints_seen: FingerprintSeen[];
  verdict: HeartbeatDetectorVerdict;
}

// ─── Audit log ───────────────────────────────────────────────────

export interface AuditLogEntry {
  id: number;
  actor_type: string;
  actor_id: string;
  action: string;
  target_type: string;
  target_id: string;
  payload: Record<string, unknown>;
  request_id: string | null;
  client_ip: string | null;
  user_agent: string | null;
  occurred_at: string;
}

export interface AuditLogListResponse {
  items: AuditLogEntry[];
  limit: number;
  offset: number;
}
