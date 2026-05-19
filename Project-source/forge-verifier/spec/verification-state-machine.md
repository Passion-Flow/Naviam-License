# Verification State Machine

Per-mode flow from `Verifier.verify_blocking()` to a returned `Result` or raised `VerificationFailed`.

All three modes share the same first phase (signature + temporal). They diverge at "network calls".

## Phase 1 — Parse & signature (all modes)

```
read .forge tar → unpack 3 entries
metadata.magic == "forg" ?         ─no→  ForgeFileMalformed
metadata.algorithm supported by SDK? ─no→ AlgorithmMismatch
signature OK against payload bytes ? ─no→ SignatureInvalid
now < payload.expires_at ?         ─no→  Expired
```

## Phase 2 — Binding (all modes if binding != none)

```
fingerprint = recompute()
hash(fingerprint) == payload.bound_fingerprint ? ─no→ BindingMismatch
```

## Phase 3 — CRL (hybrid + online)

```
crl = fetch(LA + /api/v1/revocation-list) | cached
license_id in crl ? ─yes→ Revoked
```

CRL is content-addressable — verifier caches by hash; if remote hash unchanged, served from cache. On network failure:

- `hybrid`: fall back to cached CRL ≤ `crl_grace_seconds` old; older or absent → log warning, continue (assume not revoked).
- `online`: any CRL fetch error → `VerificationFailed status=crl_unreachable`.

## Phase 4 — Heartbeat (hybrid + online)

```
POST /api/v1/licenses/{id}/heartbeat
  body  = {license_id, fingerprint, verifier_version, nonce, reported_at}
  header X-Forge-API-Key
  header X-Forge-Signature = HMAC-SHA256(body, key=derive(api_key))
```

LA response:

- `200 {"ok": true, "ttl_seconds": N}` → success; cache state in `~/.forge-verifier/heartbeat-state.json`.
- `200 {"ok": false, "reason": "..."}` → `HeartbeatRejected` (cleanup business case: revoked / quota exceeded / multi_env).
- `429` → backoff; do not fail verification.
- network error → see mode-specific behavior:
  - `hybrid` + last successful heartbeat < `online_grace_seconds` ago → continue.
  - `online` + any failure → `VerificationFailed status=heartbeat_unreachable`.

## Phase 5 — Result

If we got here, build `Result(status="valid", valid_until=expires_at)`.

## Modes summary

| Phase | offline | hybrid | online |
|-------|---------|--------|--------|
| 1 Parse + sig + expiry | ✓ | ✓ | ✓ |
| 2 Binding | ✓ | ✓ | ✓ |
| 3 CRL | — | best-effort | required |
| 4 Heartbeat | — | best-effort | required |
| 5 Result | always | always | always (if all above OK) |

## Periodic recheck

```
start_periodic_recheck(on_invalid):
  while not stopped:
    sleep(recheck_interval_seconds)
    try:
      verify()
    except VerificationFailed as e:
      on_invalid(e)
      break              ← stop loop on first failure; callers re-arm if desired
```

Background daemon thread; `stop()` flips the stopped flag and the loop exits on next tick.

## Error → status code map

| Exception | result.status | exit hint |
|-----------|---------------|-----------|
| `ForgeFileMalformed` | `malformed` | fix path / re-download |
| `AlgorithmMismatch` | `algorithm_mismatch` | wrong SDK or wrong public key |
| `SignatureInvalid` | `signature_invalid` | wrong public key or tampered file |
| `Expired` | `expired` | renew or contact LA admin |
| `BindingMismatch` | `binding_mismatch` | re-issue for new hardware |
| `Revoked` | `revoked` | contact LA admin |
| `HeartbeatRejected` | `heartbeat_rejected` | check reason field |
