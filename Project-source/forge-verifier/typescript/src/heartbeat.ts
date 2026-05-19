// Heartbeat client — POSTs to /api/v1/licenses/{id}/heartbeat with HMAC-SHA256
// body signature. Wire protocol matches the Python reference: body is sent as
// canonical-JSON (sorted keys, no whitespace) so the server can recompute the
// signature without depending on per-language JSON formatting quirks.

import { createHmac, randomBytes } from "node:crypto";

import { canonicalize } from "./canonical.js";

export interface HeartbeatRequest {
  license_id: string;
  fingerprint: string;
  verifier_version: string;
  nonce: string;
  reported_at: string;
}

export interface HeartbeatResponse {
  ok?: boolean;
  license_status: string;
  multi_env_anomaly: boolean;
  next_heartbeat_after_seconds: number;
  reason?: string;
}

export class HeartbeatError extends Error {
  constructor(message: string, public readonly status?: number) {
    super(message);
    this.name = "HeartbeatError";
  }
}

export interface HeartbeatClientOptions {
  baseUrl: string;
  apiKey: string;
  userAgent?: string;
  fetch?: typeof fetch;
}

export class HeartbeatClient {
  private readonly baseUrl: string;
  private readonly apiKey: string;
  private readonly userAgent: string;
  private readonly fetchImpl: typeof fetch;

  constructor(opts: HeartbeatClientOptions) {
    if (!opts.baseUrl) throw new Error("HeartbeatClient: baseUrl required");
    if (!opts.apiKey) throw new Error("HeartbeatClient: apiKey required");
    this.baseUrl = opts.baseUrl.replace(/\/+$/, "");
    this.apiKey = opts.apiKey;
    this.userAgent = opts.userAgent ?? "forge-verifier/typescript@0.2.0";
    this.fetchImpl = opts.fetch ?? globalThis.fetch;
  }

  async send(licenseId: string, fingerprint: string): Promise<HeartbeatResponse> {
    const body: HeartbeatRequest = {
      license_id: licenseId,
      fingerprint,
      verifier_version: this.userAgent,
      nonce: randomBytes(16).toString("hex"),
      reported_at: new Date().toISOString(),
    };
    const canonical = canonicalize(body);
    const sig = createHmac("sha256", this.apiKey).update(canonical, "utf8").digest("hex");

    const resp = await this.fetchImpl(
      `${this.baseUrl}/licenses/${encodeURIComponent(licenseId)}/heartbeat`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Forge-API-Key": this.apiKey,
          "X-Forge-Signature": `sha256=${sig}`,
          "User-Agent": this.userAgent,
        },
        body: canonical,
      },
    );
    if (resp.status === 401) throw new HeartbeatError("invalid api key (401)", 401);
    if (resp.status === 429) throw new HeartbeatError("rate limited (429)", 429);
    if (resp.status >= 500) throw new HeartbeatError(`server error ${resp.status}`, resp.status);
    if (!resp.ok) throw new HeartbeatError(`unexpected status ${resp.status}`, resp.status);
    return (await resp.json()) as HeartbeatResponse;
  }
}
