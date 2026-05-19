// Ed25519 verification via Node's built-in crypto.
// Node 18+ supports `crypto.verify('ed25519', ...)` with a raw 32-byte public key
// wrapped in SubjectPublicKeyInfo. We accept the raw 32 bytes from the LA's
// /public-keys endpoint and DER-wrap it ourselves to avoid making callers ship
// PEM/DER blobs around.

import { createPublicKey, verify as cryptoVerify } from "node:crypto";

// SubjectPublicKeyInfo prefix for ed25519 — `30 2a 30 05 06 03 2b 65 70 03 21 00`.
const ED25519_SPKI_PREFIX = new Uint8Array([
  0x30, 0x2a, 0x30, 0x05, 0x06, 0x03, 0x2b, 0x65, 0x70, 0x03, 0x21, 0x00,
]);

export function verifyEd25519(
  payloadRaw: Uint8Array,
  signature: Uint8Array,
  rawPublicKey32: Uint8Array,
): boolean {
  if (rawPublicKey32.length !== 32) {
    throw new Error(
      `ed25519: public key must be 32 raw bytes, got ${rawPublicKey32.length}`,
    );
  }
  if (signature.length !== 64) return false;

  const spki = new Uint8Array(ED25519_SPKI_PREFIX.length + 32);
  spki.set(ED25519_SPKI_PREFIX, 0);
  spki.set(rawPublicKey32, ED25519_SPKI_PREFIX.length);
  const key = createPublicKey({ key: Buffer.from(spki), format: "der", type: "spki" });
  return cryptoVerify(null, payloadRaw, key, signature);
}
