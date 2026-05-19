// Online / hybrid composition — parses + verifies signature/expiry, then
// dispatches CRL refresh + heartbeat based on the license's `mode` field.
//
// Fail-closed policy mirrors the Go / Java / C# / Rust SDKs:
//   - offline → never touches the network
//   - hybrid  → signature MUST pass; CRL + heartbeat best-effort
//               (cached CRL revoke still wins)
//   - online  → signature + CRL + heartbeat ALL MUST pass; net error → reject

import type { CrlClient } from "./crl.js";
import type { HeartbeatClient } from "./heartbeat.js";
import { parse } from "./verify.js";
import { verifyFile } from "./verify.js";
import { ForgeError, type VerifyResult } from "./types.js";

export interface OnlineVerifierOptions {
  publicKey: Uint8Array;
  heartbeat?: HeartbeatClient;
  crl?: CrlClient;
}

export class OnlineVerifier {
  constructor(private readonly opts: OnlineVerifierOptions) {}

  async verify(path: string, fingerprint: string, now: Date): Promise<VerifyResult> {
    const file = await parse(path);
    const res = verifyFile(file, this.opts.publicKey, now);
    const mode = file.payload.mode ?? "offline";
    const licenseId = file.payload.license_id;

    switch (mode) {
      case "offline":
        return res;

      case "hybrid":
        if (this.opts.crl) {
          try {
            await this.opts.crl.refresh();
          } catch {
            // hybrid: ignore network errors, fall back to cached snapshot
          }
          if (this.opts.crl.isRevoked(licenseId)) {
            throw new ForgeError("license revoked (CRL)", "revoked", {
              ...res,
              status: "revoked",
            });
          }
        }
        if (this.opts.heartbeat) {
          try {
            await this.opts.heartbeat.send(licenseId, fingerprint);
          } catch {
            // best-effort
          }
        }
        return res;

      case "online":
        if (!this.opts.crl || !this.opts.heartbeat) {
          throw new ForgeError(
            "online mode requires CrlClient + HeartbeatClient",
            "malformed",
          );
        }
        try {
          await this.opts.crl.refresh();
        } catch (e) {
          throw new ForgeError(
            `online: CRL refresh failed: ${(e as Error).message}`,
            "signature_invalid",
          );
        }
        if (this.opts.crl.isRevoked(licenseId)) {
          throw new ForgeError("license revoked", "revoked", { ...res, status: "revoked" });
        }
        try {
          const hb = await this.opts.heartbeat.send(licenseId, fingerprint);
          if (hb.license_status && hb.license_status !== "active" && hb.license_status !== "valid") {
            throw new ForgeError(
              `online: server reports license_status=${hb.license_status}`,
              "signature_invalid",
            );
          }
        } catch (e) {
          if (e instanceof ForgeError) throw e;
          throw new ForgeError(
            `online: heartbeat failed: ${(e as Error).message}`,
            "signature_invalid",
          );
        }
        return res;

      default:
        throw new ForgeError(`unknown license mode: ${mode}`, "malformed");
    }
  }
}
