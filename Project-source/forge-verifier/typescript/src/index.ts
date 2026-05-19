// Public surface — keep stable; downstream apps import only from here.

export { parse, parseBytes, verify, verifyFile } from "./verify.js";
export { OnlineVerifier, type OnlineVerifierOptions } from "./online.js";
export { computeSoftFingerprint } from "./fingerprint.js";
export {
  HeartbeatClient,
  HeartbeatError,
  type HeartbeatClientOptions,
  type HeartbeatRequest,
  type HeartbeatResponse,
} from "./heartbeat.js";
export { CrlClient, CrlError, type CrlClientOptions, type CrlResponse } from "./crl.js";
export { canonicalize } from "./canonical.js";
export {
  FORGE_MAGIC,
  FORGE_VERSION,
  ForgeError,
  type Algorithm,
  type Binding,
  type ForgeFile,
  type Metadata,
  type Mode,
  type Payload,
  type Status,
  type VerifyResult,
} from "./types.js";
