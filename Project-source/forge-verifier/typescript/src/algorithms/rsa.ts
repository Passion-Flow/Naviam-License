// RSA-PSS-SHA256 verification via Node's built-in crypto.
// Public key is DER-encoded SubjectPublicKeyInfo (see spec/algorithm-encoding.md).
// PSS params: MGF1 with SHA-256, salt length = hash length = 32 bytes.

import { createPublicKey, createVerify, constants } from "node:crypto";

export function verifyRsaPss(
  payloadRaw: Uint8Array,
  signature: Uint8Array,
  derPublicKey: Uint8Array,
  expectedBits: 2048 | 4096,
): boolean {
  const key = createPublicKey({
    key: Buffer.from(derPublicKey),
    format: "der",
    type: "spki",
  });
  const bits = (key.asymmetricKeyDetails as { modulusLength?: number } | undefined)
    ?.modulusLength;
  if (bits !== expectedBits) {
    throw new Error(`rsa: modulus is ${bits ?? "unknown"} bits, expected ${expectedBits}`);
  }
  const v = createVerify("RSA-SHA256");
  v.update(payloadRaw);
  v.end();
  return v.verify(
    {
      key,
      padding: constants.RSA_PKCS1_PSS_PADDING,
      saltLength: 32,
    },
    signature,
  );
}
