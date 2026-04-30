// 前后端共享契约的 TS 镜像。任何变更通过 /sync-api-contract 命令同步。
// 源：projects/license/src/contracts/

export type Uuid = string;
export type IsoDateTime = string;

export interface Pagination<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface ApiError {
  code: string;
  message: string;
  hint?: string;
  trace_id?: string;
}

export interface User {
  id: Uuid;
  username: string;
  email: string;
  is_superadmin: boolean;
  must_change_pw: boolean;
  totp_confirmed: boolean;
  last_login_at?: IsoDateTime | null;
}

export interface Customer {
  id: Uuid;
  display_name: string;
  legal_name?: string | null;
  contact_name?: string | null;
  contact_email?: string | null;
  contact_phone?: string | null;
  region?: string | null;
  notes?: string | null;
  created_at: IsoDateTime;
  updated_at: IsoDateTime;
}

export interface Product {
  id: Uuid;
  code: string;
  display_name: string;
  schema_version: number;
  description?: string | null;
}

export type LicenseStatus =
  | "draft"
  | "issued"
  | "active"
  | "expired"
  | "grace"
  | "sunset"
  | "revoked";

export interface License {
  id: Uuid;
  license_id: string;
  product_code: string;
  customer_id: Uuid;
  cloud_id_text: string;
  status: LicenseStatus;
  issued_at?: IsoDateTime | null;
  not_before?: IsoDateTime | null;
  expires_at: IsoDateTime;
  grace_until?: IsoDateTime | null;
  signature_kid: string;
  notes?: string | null;
}
