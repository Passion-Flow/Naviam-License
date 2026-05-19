# `.forge` File Layout

Forge license files are **ustar tarballs** (POSIX 1003.1-1988) containing exactly three entries. Format is the same across all language SDKs.

## Top-level structure

```
license.forge   ← uncompressed ustar tar
├── payload.json     ← canonical JSON; the bytes signed by the LA
├── signature.bin    ← raw signature bytes (no header, no PEM)
└── metadata.json    ← algorithm + key_id + signed_at header
```

Order is **not** stable. Verifier MUST look up entries by name, not position.

### Why no compression?

- `.forge` files are tiny (typically 500B–4KB). gzip overhead > savings.
- ustar without gzip means any environment can `tar -tf license.forge` to inspect.
- Tar checksum survives mangled MIME / line-endings.

### Why tar instead of a flat JSON?

- Need to embed binary `signature.bin` without base64 re-encoding (binary safety + size).
- Signature MUST cover **exact bytes** of `payload.json`. Embedding payload as a JSON string-of-JSON requires escaping rules; tar avoids this entirely.

## Per-entry rules

### `payload.json`

- Encoding: UTF-8, no BOM.
- Format: **canonical JSON**, RFC 8785 subset:
  - keys sorted lexicographically
  - no insignificant whitespace
  - numbers serialised as shortest unique form
  - ISO 8601 `Z` UTC datetimes (`2026-05-18T00:00:00+00:00`)
- The exact bytes of this entry are what `signature.bin` covers. SDKs MUST NOT re-serialise.

Fields: see `payload-schema.json`.

### `signature.bin`

Raw signature output of the algorithm:

| algorithm  | length            | format |
|------------|-------------------|--------|
| `ed25519`  | 64 B              | r ‖ s (RFC 8032), raw bytes |
| `rsa2048`  | 256 B             | RSASSA-PSS-SHA256 with MGF1-SHA256, salt = hash length (32 B), raw bytes |
| `rsa4096`  | 512 B             | same as rsa2048, raw bytes |
| `sm2`      | ~128 ASCII chars  | **ASCII-hex** of GM/T 0003.2-2012 raw `r ‖ s`. Public key in `payload`/external storage is likewise ASCII-hex (128 chars, uncompressed X ‖ Y). |

> **SM2 wire-format note**: unlike Ed25519/RSA which embed raw bytes, SM2 uses
> ASCII-hex inside `signature.bin` and for public keys. This matches the Python
> reference implementation (`gmssl.sm2`) which works in hex strings, and is
> kept consistent across all language SDKs (Go / Java / C# / Rust / TypeScript).
> The trade-off (2× size) is irrelevant given how small `.forge` files are.

### `metadata.json`

Canonical JSON, fields:

```json
{
  "magic": "forg",
  "forge_version": "1.0",
  "algorithm": "ed25519",
  "key_id": "ed25519-2026-q1",
  "signed_at": "2026-05-18T00:00:00+00:00"
}
```

- `magic` MUST equal `"forg"`. Verifier MUST reject otherwise (sentinel: forge-file-malformed).
- `forge_version` follows semver-ish MAJOR.MINOR. Major bumps are wire-breaking.
- `key_id` lets the verifier pick the right public key when multiple are pinned.
- `signed_at` is informational; verification does NOT depend on it. (Use `payload.expires_at` for temporal checks.)

## Future-compat rules

- Verifiers MUST **ignore** unknown tar entries (forward compat for future fields).
- Verifiers MUST **reject** missing required entries (signature / payload / metadata).
- Verifiers MUST NOT attempt to "fix" malformed JSON; reject as malformed.
- Wire-breaking changes get a new `forge_version` value.

## Generation reference

```python
# forge-server side (reference)
import io, json, tarfile

def pack(payload_bytes: bytes, signature: bytes, metadata: dict) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.USTAR_FORMAT) as tf:
        for name, data in [
            ("payload.json", payload_bytes),
            ("signature.bin", signature),
            ("metadata.json", json.dumps(metadata, separators=(",", ":"), sort_keys=True).encode()),
        ]:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()
```
