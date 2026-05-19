# Binding Fingerprint

How the verifier collects the deployment fingerprint and how the LA binds licenses to it.

## Levels

| Level | What is collected | Stability | Use case |
|-------|-------------------|-----------|----------|
| `none` | nothing | n/a | trial / dev licenses |
| `soft` | MAC + hostname + CPU vendor id | survives reboots; changes on hardware swap | default for licensed software |
| `hard` | soft components + TPM / SE / SmartCard platform UUID | survives full OS reinstall | regulated industries; high anti-piracy |

## Canonical fingerprint string (soft)

The verifier concatenates, in this order:

```
<primary-mac-address>|<hostname>|<cpu-vendor>:<cpu-family>:<cpu-model>
```

- `primary-mac-address` = first non-loopback, non-virtual NIC's MAC, lowercased, colon-separated (`aa:bb:cc:dd:ee:ff`).
- `hostname` = `os.uname().nodename` (or platform equivalent), lowercased, ASCII only.
- CPU fields:
  - Linux: parse `/proc/cpuinfo`; `vendor_id`, `cpu family`, `model`.
  - macOS: `sysctl -n machdep.cpu.{vendor,family,model}`.
  - Windows: `wmic CPU get Manufacturer,Family,Model /value`.

If a component cannot be obtained (e.g. CPU info on a container without `/proc`), substitute the literal `unknown`. SDK MUST NOT silently drop the field — that would make the hash unstable.

## Hard fingerprint extra

Append `|tpm:<sha256 of PCR0..PCR7>` or `|se:<platform-uuid>`. Concrete platform-specific extraction is out of scope for this spec; SDKs SHOULD document what they read.

## Hash

```
bound_fingerprint = SHA-256(canonical_string).hex()
```

64-char lowercase hex string. Stored in `.forge/payload.json::bound_fingerprint`.

## Verifier behavior

1. On `verify_blocking()`, recompute fingerprint.
2. If `payload.binding == "none"` → skip.
3. If `payload.binding == "soft"` → recomputed hex MUST equal `payload.bound_fingerprint`. Mismatch → `BindingMismatch`.
4. If `payload.binding == "hard"` → same comparison; recomputed canonical string MUST include the TPM/SE extra component. Mismatch → `BindingMismatch`.

## Multi-environment detection (LA side)

LA records every heartbeat's fingerprint. If a single `license_id` shows ≥ N distinct fingerprints within `HEARTBEAT_ANOMALY_WINDOW_SECONDS`, LA writes an audit `heartbeat.anomaly_detected` event and may reject subsequent heartbeats (`HeartbeatRejected reason=multi_env`).

Default `N = 3` over `1 hour` (settings.heartbeat_anomaly_threshold / heartbeat_anomaly_window_seconds).

## Sample (illustrative — not real bytes)

```
canonical: "aa:bb:cc:dd:ee:ff|prod-app-01|GenuineIntel:6:142"
sha256:    "1f3a...c7d2" (64 hex chars)
```
