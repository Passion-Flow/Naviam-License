// CRL (Certificate Revocation List) client — GETs /api/v1/revocation-list with
// ETag / If-None-Match. On 304 we keep the cached snapshot. Reuse a single
// instance — it caches both the revoked set and the ETag in memory.

export interface CrlResponse {
  license_ids: string[];
  generated_at: string;
}

export class CrlError extends Error {
  constructor(message: string, public readonly status?: number) {
    super(message);
    this.name = "CrlError";
  }
}

export interface CrlClientOptions {
  baseUrl: string;
  apiKey?: string;
  userAgent?: string;
  fetch?: typeof fetch;
}

export class CrlClient {
  private readonly baseUrl: string;
  private readonly apiKey: string;
  private readonly userAgent: string;
  private readonly fetchImpl: typeof fetch;

  private revoked = new Set<string>();
  private etag = "";
  private lastFetched: Date | null = null;

  constructor(opts: CrlClientOptions) {
    if (!opts.baseUrl) throw new Error("CrlClient: baseUrl required");
    this.baseUrl = opts.baseUrl.replace(/\/+$/, "");
    this.apiKey = opts.apiKey ?? "";
    this.userAgent = opts.userAgent ?? "forge-verifier/typescript@0.2.0";
    this.fetchImpl = opts.fetch ?? globalThis.fetch;
  }

  async refresh(): Promise<void> {
    const headers: Record<string, string> = {
      Accept: "application/json",
      "User-Agent": this.userAgent,
    };
    if (this.apiKey) headers["X-Forge-API-Key"] = this.apiKey;
    if (this.etag) headers["If-None-Match"] = this.etag;

    const resp = await this.fetchImpl(`${this.baseUrl}/revocation-list`, { headers });
    if (resp.status === 304) {
      this.lastFetched = new Date();
      return;
    }
    if (resp.status === 401) throw new CrlError("invalid api key (401)", 401);
    if (resp.status === 429) throw new CrlError("rate limited (429)", 429);
    if (resp.status >= 500) throw new CrlError(`server error ${resp.status}`, resp.status);
    if (!resp.ok) throw new CrlError(`unexpected status ${resp.status}`, resp.status);

    const body = (await resp.json()) as CrlResponse;
    this.revoked = new Set(body.license_ids ?? []);
    this.etag = resp.headers.get("etag") ?? "";
    this.lastFetched = new Date();
  }

  isRevoked(licenseId: string): boolean {
    return this.revoked.has(licenseId);
  }

  size(): number {
    return this.revoked.size;
  }

  getLastFetched(): Date | null {
    return this.lastFetched;
  }
}
