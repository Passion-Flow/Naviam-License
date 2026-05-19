// Soft fingerprint — SHA-256 over (MAC | hostname | CPU). Lowercase hex.
// Matches the Go / Python / Java / C# / Rust SDKs byte-for-byte: a license bound
// on one host can be verified by any-language verifier on the same host.

import { createHash } from "node:crypto";
import { hostname, networkInterfaces, arch, platform, cpus } from "node:os";

export function computeSoftFingerprint(): string {
  const mac = safe(primaryMac());
  const host = safe(hostname());
  const cpu = safe(cpuDescription());
  const canonical = `${mac}|${host}|${cpu}`.toLowerCase();
  return createHash("sha256").update(canonical, "utf8").digest("hex");
}

function primaryMac(): string {
  const ifs = networkInterfaces();
  for (const [name, addrs] of Object.entries(ifs)) {
    if (!addrs || addrs.length === 0) continue;
    const lname = name.toLowerCase();
    if (
      lname.startsWith("lo") ||
      lname.startsWith("docker") ||
      lname.startsWith("veth") ||
      lname.startsWith("vmnet") ||
      lname.startsWith("br-") ||
      lname.startsWith("utun")
    ) {
      continue;
    }
    for (const a of addrs) {
      if (a.internal) continue;
      if (a.mac && a.mac !== "00:00:00:00:00:00") return a.mac.toLowerCase();
    }
  }
  return "";
}

function cpuDescription(): string {
  const list = cpus();
  return `${arch()}:${platform()}:${list.length}`;
}

function safe(s: string): string {
  return s === "" ? "unknown" : s;
}
