// Parse + verify entry-point. Mirrors `forge-verifier/python` and `go` SDKs.

import { readFile } from "node:fs/promises";

import { verifyEd25519 } from "./algorithms/ed25519.js";
import { verifyRsaPss } from "./algorithms/rsa.js";
import { verifySm2 } from "./algorithms/sm2.js";
import { readTar } from "./tar.js";
import {
  FORGE_MAGIC,
  ForgeError,
  type ForgeFile,
  type Metadata,
  type Payload,
  type VerifyResult,
} from "./types.js";

/** One-shot: load file from disk, parse, verify. */
export async function verify(
  path: string,
  publicKey: Uint8Array,
  now: Date,
): Promise<VerifyResult> {
  const bytes = await readFile(path);
  const file = parseBytes(bytes);
  return verifyFile(file, publicKey, now);
}

/** Parse a `.forge` file from disk without doing any crypto. */
export async function parse(path: string): Promise<ForgeFile> {
  return parseBytes(await readFile(path));
}

/** Parse a `.forge` archive from its raw bytes. */
export function parseBytes(bytes: Uint8Array): ForgeFile {
  const entries = readTar(bytes);
  let payloadRaw: Uint8Array | undefined;
  let signature: Uint8Array | undefined;
  let metadata: Metadata | undefined;
  for (const e of entries) {
    if (e.name === "payload.json") payloadRaw = e.content;
    else if (e.name === "signature.bin") signature = e.content;
    else if (e.name === "metadata.json") {
      metadata = JSON.parse(new TextDecoder("utf-8").decode(e.content)) as Metadata;
    }
  }
  if (!payloadRaw || !signature || !metadata) {
    throw new ForgeError("forge file missing required entry", "malformed");
  }
  if (metadata.magic !== FORGE_MAGIC) {
    throw new ForgeError(`bad magic: ${metadata.magic}`, "malformed");
  }
  let payload: Payload;
  try {
    payload = JSON.parse(new TextDecoder("utf-8").decode(payloadRaw)) as Payload;
  } catch (e) {
    throw new ForgeError(`payload.json malformed: ${(e as Error).message}`, "malformed");
  }
  return { payload, payloadRaw, signature, metadata };
}

/** Verify an already-parsed file. */
export function verifyFile(
  file: ForgeFile,
  publicKey: Uint8Array,
  now: Date,
): VerifyResult {
  const result: VerifyResult = {
    status: "valid",
    licenseId: file.payload.license_id,
    expiresAt: file.payload.expires_at,
    binding: file.payload.binding,
    fingerprintMustMatch: file.payload.bound_fingerprint ?? null,
  };

  let ok: boolean;
  switch (file.metadata.algorithm) {
    case "ed25519":
      ok = verifyEd25519(file.payloadRaw, file.signature, publicKey);
      break;
    case "rsa2048":
      ok = verifyRsaPss(file.payloadRaw, file.signature, publicKey, 2048);
      break;
    case "rsa4096":
      ok = verifyRsaPss(file.payloadRaw, file.signature, publicKey, 4096);
      break;
    case "sm2":
      ok = verifySm2(file.payloadRaw, file.signature, publicKey);
      break;
    default:
      throw new ForgeError(
        `algorithm unsupported: ${file.metadata.algorithm}`,
        "algorithm_unsupported",
      );
  }
  if (!ok) {
    throw new ForgeError("signature invalid", "signature_invalid", {
      ...result,
      status: "signature_invalid",
    });
  }

  const expires = new Date(file.payload.expires_at);
  if (now.getTime() >= expires.getTime()) {
    throw new ForgeError("license expired", "expired", { ...result, status: "expired" });
  }
  return result;
}
