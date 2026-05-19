// Shared types — keep field names consistent with payload-schema.json.

export const FORGE_MAGIC = "forg";
export const FORGE_VERSION = "1.0";

export type Algorithm = "ed25519" | "rsa2048" | "rsa4096" | "sm2";
export type Mode = "offline" | "hybrid" | "online";
export type Binding = "none" | "soft" | "hard";

export type Status =
  | "valid"
  | "expired"
  | "revoked"
  | "signature_invalid"
  | "algorithm_unsupported"
  | "malformed";

export interface Metadata {
  magic: string;
  forge_version: string;
  algorithm: Algorithm;
  key_id: string;
  signed_at: string;
}

export interface Payload {
  protocol_version: string;
  license_id: string;
  customer_id: string;
  product_id: string;
  mode: Mode;
  scope: string;
  binding: Binding;
  bound_fingerprint?: string | null;
  issued_at: string;
  expires_at: string;
  features: Record<string, unknown>;
  limits: Record<string, unknown>;
}

export interface ForgeFile {
  payload: Payload;
  payloadRaw: Uint8Array;
  signature: Uint8Array;
  metadata: Metadata;
}

export interface VerifyResult {
  status: Status;
  licenseId: string;
  expiresAt: string;
  binding: Binding;
  fingerprintMustMatch: string | null;
}

export class ForgeError extends Error {
  constructor(
    message: string,
    public readonly status: Status,
    public readonly result?: VerifyResult,
  ) {
    super(message);
    this.name = "ForgeError";
  }
}
