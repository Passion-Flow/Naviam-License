# Algorithm Encoding

Public key and signature byte formats across the four supported algorithms.

## Ed25519

| | bytes | format |
|--|------|--------|
| Public key | 32 | raw (RFC 8032 §5.1.5) |
| Private key | 32 | raw seed; expand to 64-byte secret as per spec |
| Signature | 64 | r ‖ s (little-endian) |

JCA / .NET need the X.509 SubjectPublicKeyInfo wrapper. SDKs provide a helper; see
`forge-verifier/java/.../ForgeVerifier.java::ed25519X509` for the constant prefix.

## RSA-PSS (rsa2048 / rsa4096)

| | bytes | format |
|--|------|--------|
| Public key | 270–550 | DER-encoded SubjectPublicKeyInfo |
| Signature  | 256 (2048) / 512 (4096) | raw RSASSA-PSS output |

PSS parameters (MUST match LA + verifier):

- Hash: SHA-256
- MGF: MGF1 with SHA-256
- Salt length: 32 bytes (== hash length)
- Trailer field: 0xBC (default)

## SM2 (GM/T 0003.2-2012)

| | bytes | format |
|--|------|--------|
| Public key | 65 | uncompressed point: `0x04 ‖ X ‖ Y` (each coord 32 B) |
| Signature  | 64 | r ‖ s (big-endian) — **not** DER |

Key parameters: SM2 curve (256-bit), as defined in GB/T 32918.5-2017 Appendix D.

ZA (user identity) hash uses default `1234567812345678` per GM/T 0003.2 §A.1.

## Encoding conventions across SDKs

- Public keys exposed to applications are always **base64 (standard, padded)** strings.
  Languages' raw-byte input methods accept the decoded bytes; helpers handle b64 internally.
- Signatures are stored raw in `.forge/signature.bin`; SDKs read length-checked bytes.
- Key IDs are 16-byte hex strings (`secrets.token_hex(8)`), 32 chars; format is opaque outside LA.

## Algorithm selection table

| Use case | Recommended |
|----------|-------------|
| Default / new deployments | `ed25519` |
| FIPS / .NET ecosystem | `rsa2048` |
| Compliance-mandated high-strength | `rsa4096` |
| 中国商密合规 | `sm2` |
