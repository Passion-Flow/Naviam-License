# Error Codes

Unified error code dictionary. All language SDKs MUST raise exceptions whose `status` field maps to one of these strings exactly.

## Format

`<category>.<reason>` — lowercase + dots.

## Codes

| Code | When | Recovery hint |
|------|------|---------------|
| `forge_file.missing` | License file path doesn't exist | check `license_file_path` |
| `forge_file.malformed` | Not a valid ustar tar / missing required entry / bad magic | re-download from LA |
| `forge_file.tampered` | Entries present but JSON parse fails | re-download |
| `algorithm.mismatch` | `metadata.algorithm` not in `[ed25519, rsa2048, rsa4096, sm2]` or different from caller's public key type | use correct algorithm key |
| `algorithm.unsupported` | SDK build doesn't include this algorithm (e.g. C# without BouncyCastle for SM2) | install extras |
| `signature.invalid` | crypto verify returned false | wrong public key or tampered payload |
| `temporal.not_yet_valid` | `payload.issued_at` > now (clock skew or pre-dated license) | sync clock |
| `temporal.expired` | `payload.expires_at` ≤ now | renew license |
| `binding.mismatch` | Recomputed fingerprint ≠ `payload.bound_fingerprint` | re-issue for current hardware |
| `binding.unsupported` | `binding=hard` but TPM/SE not available on this platform | use `soft` or different platform |
| `revocation.revoked` | `license_id` present in CRL | contact LA admin |
| `revocation.crl_unreachable` | online mode + cannot fetch CRL | check network to LA |
| `heartbeat.unreachable` | online mode + heartbeat endpoint not reachable | check network |
| `heartbeat.rejected` | LA responded `{"ok": false, "reason": "..."}` | inspect `reason` |
| `heartbeat.multi_env_detected` | LA detected anomalous fingerprint variation | client violating single-instance binding |
| `heartbeat.quota_exceeded` | Per-product or per-key quota hit | upgrade plan |
| `api_key.invalid` | LA rejected API key | rotate key on LA admin UI |
| `api_key.expired` | API key past its TTL | issue a new key |

## SDK-side mapping

Each SDK maps its native error types to these codes:

- **Python**: `forge_verifier.exceptions.<Type>().status` → one of the above strings.
- **Go**: `errors.Is(err, ErrXxx)` → use `result.Status` field for the code.
- **Java**: `ForgeException.status` + `Status` enum entries named in PascalCase: `MALFORMED`, `SIGNATURE_INVALID`, etc. Mapping table in javadoc.
- **C#**: `ForgeException.Status` enum, PascalCase.
- **Rust**: `ForgeError` enum variants; serialise to strings via `serde`.

## Logging in client apps

When logging a verification failure, include:

- `status` (this code)
- `license_id` (if extractable)
- `expires_at` / `bound_fingerprint` truncated
- **NEVER** the API key, the public/private key, or the raw signature

## Wire format (HeartbeatRejected reason field)

The LA-side `reason` returned with `{"ok": false}` SHOULD use one of:

- `revoked`
- `multi_env`
- `quota_exceeded`
- `binding_mismatch`
- `unknown_license`

Verifier maps the reason into the corresponding `heartbeat.*` code from the table above.
