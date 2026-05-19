//! Forge License Authority Verifier — minimum viable Rust SDK.
//!
//! Supports Ed25519 + parse + signature + expiry. RSA-PSS / SM2 / heartbeat / binding
//! are TODOs documented in README. Wire format & test vectors are shared across all
//! language SDKs (`forge-verifier/spec/test-vectors`).

use std::collections::HashMap;
use std::fs::File;
use std::io::Read;
use std::path::Path;

use chrono::{DateTime, Utc};
use ed25519_dalek::{Signature, Verifier as Ed25519VerifierTrait, VerifyingKey, SIGNATURE_LENGTH};
use rsa::pkcs8::DecodePublicKey;
use rsa::pss::{Signature as PssSignature, VerifyingKey as PssVerifyingKey};
use rsa::{traits::PublicKeyParts, RsaPublicKey};
use serde::{Deserialize, Serialize};
use sha2::Sha256;
use signature::Verifier as SigVerifier;
use thiserror::Error;

pub mod binding;
pub mod crl;
pub mod heartbeat;
pub mod online;
mod sm2;

pub const FORGE_MAGIC: &str = "forg";
pub const FORGE_VERSION: &str = "1.0";

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Status {
    Valid,
    Expired,
    Revoked,
    SignatureInvalid,
    AlgorithmUnsupported,
    Malformed,
}

#[derive(Debug, Clone, Deserialize)]
pub struct Metadata {
    pub magic: String,
    pub forge_version: String,
    pub algorithm: String,
    pub key_id: String,
    pub signed_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct Payload {
    pub protocol_version: String,
    pub license_id: String,
    pub customer_id: String,
    pub product_id: String,
    pub mode: String,
    pub scope: String,
    pub binding: String,
    pub bound_fingerprint: Option<String>,
    pub issued_at: DateTime<Utc>,
    pub expires_at: DateTime<Utc>,
    pub features: HashMap<String, serde_json::Value>,
    pub limits: HashMap<String, serde_json::Value>,
}

#[derive(Debug, Clone, Serialize)]
pub struct VerifyResult {
    pub status: Status,
    pub license_id: String,
    pub expires_at: DateTime<Utc>,
    pub binding: String,
    pub fingerprint_must_match: Option<String>,
}

#[derive(Debug, Error)]
pub enum ForgeError {
    #[error("forge file malformed: {0}")]
    Malformed(String),
    #[error("algorithm unsupported: {0}")]
    AlgorithmUnsupported(String),
    #[error("signature invalid")]
    SignatureInvalid,
    #[error("license expired (id={license_id})")]
    Expired {
        license_id: String,
        result: VerifyResult,
    },
    #[error("license revoked (id={license_id})")]
    Revoked {
        license_id: String,
        result: VerifyResult,
    },
    #[error("online mode required CrlClient + HeartbeatClient")]
    OnlineRequiresClients,
    #[error("online: {0}")]
    OnlineFailed(String),
    #[error("unknown license mode: {0}")]
    UnknownMode(String),
}

pub struct ForgeFile {
    pub payload: Payload,
    pub payload_raw: Vec<u8>,
    pub signature: Vec<u8>,
    pub metadata: Metadata,
}

pub fn verify(
    path: impl AsRef<Path>,
    public_key: &[u8],
    now: DateTime<Utc>,
) -> Result<VerifyResult, ForgeError> {
    let f = parse(path)?;
    f.verify(public_key, now)
}

pub fn parse(path: impl AsRef<Path>) -> Result<ForgeFile, ForgeError> {
    let file = File::open(&path).map_err(|e| ForgeError::Malformed(e.to_string()))?;
    let mut archive = tar::Archive::new(file);

    let mut payload_raw: Option<Vec<u8>> = None;
    let mut signature: Option<Vec<u8>> = None;
    let mut metadata: Option<Metadata> = None;

    for entry in archive
        .entries()
        .map_err(|e| ForgeError::Malformed(e.to_string()))?
    {
        let mut entry = entry.map_err(|e| ForgeError::Malformed(e.to_string()))?;
        let name = entry
            .path()
            .map_err(|e| ForgeError::Malformed(e.to_string()))?
            .to_string_lossy()
            .into_owned();
        let mut buf = Vec::new();
        entry
            .read_to_end(&mut buf)
            .map_err(|e| ForgeError::Malformed(e.to_string()))?;
        match name.as_str() {
            "payload.json" => payload_raw = Some(buf),
            "signature.bin" => signature = Some(buf),
            "metadata.json" => {
                metadata = Some(
                    serde_json::from_slice(&buf)
                        .map_err(|e| ForgeError::Malformed(format!("metadata.json: {e}")))?,
                );
            }
            _ => { /* unknown entry — forward-compat ignore */ }
        }
    }

    let payload_raw = payload_raw.ok_or_else(|| ForgeError::Malformed("missing payload.json".into()))?;
    let signature = signature.ok_or_else(|| ForgeError::Malformed("missing signature.bin".into()))?;
    let metadata = metadata.ok_or_else(|| ForgeError::Malformed("missing metadata.json".into()))?;

    if metadata.magic != FORGE_MAGIC {
        return Err(ForgeError::Malformed(format!("bad magic: {}", metadata.magic)));
    }
    let payload: Payload = serde_json::from_slice(&payload_raw)
        .map_err(|e| ForgeError::Malformed(format!("payload.json: {e}")))?;

    Ok(ForgeFile {
        payload,
        payload_raw,
        signature,
        metadata,
    })
}

impl ForgeFile {
    pub fn verify(&self, public_key: &[u8], now: DateTime<Utc>) -> Result<VerifyResult, ForgeError> {
        let mut result = VerifyResult {
            status: Status::Valid,
            license_id: self.payload.license_id.clone(),
            expires_at: self.payload.expires_at,
            binding: self.payload.binding.clone(),
            fingerprint_must_match: self.payload.bound_fingerprint.clone(),
        };

        match self.metadata.algorithm.as_str() {
            "ed25519" => self.verify_ed25519(public_key)?,
            "rsa2048" | "rsa4096" => {
                let expected_bits = if self.metadata.algorithm == "rsa4096" { 4096 } else { 2048 };
                self.verify_rsa_pss(public_key, expected_bits)?;
            }
            "sm2" => {
                if !crate::sm2::verify(&self.payload_raw, public_key, &self.signature) {
                    return Err(ForgeError::SignatureInvalid);
                }
            }
            other => {
                return Err(ForgeError::AlgorithmUnsupported(other.to_string()));
            }
        }

        if now >= self.payload.expires_at {
            result.status = Status::Expired;
            return Err(ForgeError::Expired {
                license_id: result.license_id.clone(),
                result,
            });
        }
        Ok(result)
    }

    fn verify_rsa_pss(&self, der_public_key: &[u8], expected_bits: usize) -> Result<(), ForgeError> {
        let pk = RsaPublicKey::from_public_key_der(der_public_key)
            .map_err(|_| ForgeError::SignatureInvalid)?;
        let bits = pk.size() * 8;
        if bits != expected_bits {
            return Err(ForgeError::SignatureInvalid);
        }
        // salt length = hash length (32 B) is the default for VerifyingKey::<Sha256>::new
        let vk: PssVerifyingKey<Sha256> = PssVerifyingKey::new(pk);
        let sig = PssSignature::try_from(self.signature.as_slice())
            .map_err(|_| ForgeError::SignatureInvalid)?;
        vk.verify(&self.payload_raw, &sig)
            .map_err(|_| ForgeError::SignatureInvalid)
    }

    fn verify_ed25519(&self, public_key: &[u8]) -> Result<(), ForgeError> {
        let pk_bytes: [u8; 32] = public_key
            .try_into()
            .map_err(|_| ForgeError::SignatureInvalid)?;
        let pk = VerifyingKey::from_bytes(&pk_bytes).map_err(|_| ForgeError::SignatureInvalid)?;
        if self.signature.len() != SIGNATURE_LENGTH {
            return Err(ForgeError::SignatureInvalid);
        }
        let sig_bytes: [u8; SIGNATURE_LENGTH] = self
            .signature
            .as_slice()
            .try_into()
            .map_err(|_| ForgeError::SignatureInvalid)?;
        let sig = Signature::from_bytes(&sig_bytes);
        pk.verify(&self.payload_raw, &sig)
            .map_err(|_| ForgeError::SignatureInvalid)
    }
}
