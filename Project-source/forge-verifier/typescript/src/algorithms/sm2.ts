// SM2 verification — GM/T 0003.2-2012. Requires the optional `sm-crypto`
// dependency (Node ecosystem has no first-party SM2). Callers who don't
// service Chinese信创 customers can omit the dep and never import this file.

import { createRequire } from "node:module";

interface SmCryptoSm2 {
  doVerifySignature: (
    msg: string | Uint8Array,
    sig: string,
    publicKey: string,
    options?: { hash?: boolean; userId?: string },
  ) => boolean;
}

let cached: SmCryptoSm2 | null = null;

function loadSm2(): SmCryptoSm2 {
  if (cached) return cached;
  try {
    const require = createRequire(import.meta.url);
    const mod = require("sm-crypto") as { sm2: SmCryptoSm2 };
    cached = mod.sm2;
    return cached;
  } catch (e) {
    throw new Error(
      "sm2: optional dependency 'sm-crypto' is not installed. " +
        "Run `npm install sm-crypto` to enable SM2 verification.",
    );
  }
}

export function verifySm2(
  payloadRaw: Uint8Array,
  signature: Uint8Array,
  publicKey: Uint8Array,
): boolean {
  const sm2 = loadSm2();
  // signature.bin holds ASCII-hex bytes (see spec/forge-file-layout.md).
  // publicKey is also ASCII-hex (128 chars X‖Y, no SEC1 prefix). sm-crypto wants
  // a SEC1 uncompressed key (`04` || X || Y = 130 hex chars), so prepend if needed.
  const sigHex = new TextDecoder("ascii").decode(signature);
  let pubHex = new TextDecoder("ascii").decode(publicKey);
  if (pubHex.length === 128) pubHex = "04" + pubHex;
  // sm-crypto's `doVerifySignature` treats `msg` as UTF-8 and re-encodes it;
  // for binary payloads we pre-convert to a number[] array — that branch in
  // sm-crypto's `utf8ToHex` skips the UTF-8 dance and uses the bytes verbatim,
  // matching gmssl's `verify_with_sm3(sig_hex, payload_bytes)` behavior.
  const payloadArr = Array.from(payloadRaw);
  // userId defaults to the GM/T spec value "1234567812345678" — match Python ref.
  return sm2.doVerifySignature(payloadArr as unknown as Uint8Array, sigHex, pubHex, {
    hash: true,
    userId: "1234567812345678",
  });
}

