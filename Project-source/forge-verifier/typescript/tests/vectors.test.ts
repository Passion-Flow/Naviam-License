// Cross-language vector tests — same `.forge` files all SDKs validate against.

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

import { ForgeError, verify } from "../src/index.js";

const here = dirname(fileURLToPath(import.meta.url));
const VECTORS_DIR = join(here, "..", "..", "spec", "test-vectors");

interface Keypair {
  algorithm: string;
  key_id: string;
  private_key_b64: string;
  public_key_b64: string;
}

interface Expected {
  status: string;
  license_id: string;
  binding: string;
  expires_at: string;
  fingerprint_must_match: string | null;
}

async function loadVector(name: string) {
  const dir = join(VECTORS_DIR, name);
  const keypair = JSON.parse(await readFile(join(dir, "keypair.json"), "utf8")) as Keypair;
  const expected = JSON.parse(
    await readFile(join(dir, "expected-verify.json"), "utf8"),
  ) as Expected;
  return {
    forgePath: join(dir, "expected.forge"),
    publicKey: new Uint8Array(Buffer.from(keypair.public_key_b64, "base64")),
    expected,
  };
}

test("vector 001 — ed25519/offline/none → valid", async () => {
  const v = await loadVector("001-ed25519-offline-none");
  const res = await verify(v.forgePath, v.publicKey, new Date("2026-06-01T00:00:00Z"));
  assert.equal(res.status, "valid");
  assert.equal(res.licenseId, v.expected.license_id);
  assert.equal(res.binding, "none");
});

test("vector 002 — ed25519/hybrid/soft → valid", async () => {
  const v = await loadVector("002-ed25519-hybrid-soft");
  const res = await verify(v.forgePath, v.publicKey, new Date("2026-06-01T00:00:00Z"));
  assert.equal(res.status, "valid");
});

test("vector 003 — ed25519/offline/hard → valid", async () => {
  const v = await loadVector("003-ed25519-offline-hard");
  const res = await verify(v.forgePath, v.publicKey, new Date("2026-06-01T00:00:00Z"));
  assert.equal(res.status, "valid");
  assert.equal(res.fingerprintMustMatch, v.expected.fingerprint_must_match);
});

test("expired clock → ForgeError(expired)", async () => {
  const v = await loadVector("001-ed25519-offline-none");
  await assert.rejects(
    () => verify(v.forgePath, v.publicKey, new Date("2099-01-01T00:00:00Z")),
    (err: unknown) => err instanceof ForgeError && err.status === "expired",
  );
});

test("wrong public key → ForgeError(signature_invalid)", async () => {
  const v = await loadVector("001-ed25519-offline-none");
  const tampered = new Uint8Array(v.publicKey);
  tampered[0] = (tampered[0]! ^ 0xff) & 0xff;
  await assert.rejects(
    () => verify(v.forgePath, tampered, new Date("2026-06-01T00:00:00Z")),
    (err: unknown) => err instanceof ForgeError && err.status === "signature_invalid",
  );
});

test("vector 004 — sm2/offline/none → valid (cross-language)", async () => {
  const v = await loadVector("004-sm2-offline-none");
  const res = await verify(v.forgePath, v.publicKey, new Date("2026-06-01T00:00:00Z"));
  assert.equal(res.status, "valid");
  assert.equal(res.licenseId, v.expected.license_id);
});
