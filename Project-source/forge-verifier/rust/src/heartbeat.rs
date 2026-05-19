//! Heartbeat client — POSTs to `/api/v1/licenses/{id}/heartbeat` with HMAC-SHA256
//! body signature. Wire format matches Go / Python SDKs byte-for-byte.

use chrono::Utc;
use hmac::{Hmac, Mac};
use rand::RngCore;
use serde::{Deserialize, Serialize};
use sha2::Sha256;
use thiserror::Error;

type HmacSha256 = Hmac<Sha256>;

#[derive(Debug, Error)]
pub enum HeartbeatError {
    #[error("invalid api key (401)")]
    InvalidApiKey,
    #[error("rate limited (429)")]
    RateLimited,
    #[error("server error {0}")]
    ServerError(u16),
    #[error("transport error: {0}")]
    Transport(String),
    #[error("malformed response: {0}")]
    Malformed(String),
}

#[derive(Debug, Serialize)]
pub struct HeartbeatRequest {
    pub license_id: String,
    pub fingerprint: String,
    pub verifier_version: String,
    pub nonce: String,
    pub reported_at: String,
}

#[derive(Debug, Deserialize)]
pub struct HeartbeatResponse {
    #[serde(default)]
    pub ok: bool,
    pub license_status: String,
    #[serde(default)]
    pub multi_env_anomaly: bool,
    pub next_heartbeat_after_seconds: u32,
    #[serde(default)]
    pub reason: Option<String>,
}

/// Reusable client. Cheap to clone (holds a `ureq::Agent`).
#[derive(Clone)]
pub struct HeartbeatClient {
    pub base_url: String,
    pub api_key: String,
    pub user_agent: String,
    agent: ureq::Agent,
}

impl HeartbeatClient {
    pub fn new(base_url: impl Into<String>, api_key: impl Into<String>, user_agent: impl Into<String>) -> Self {
        Self {
            base_url: base_url.into(),
            api_key: api_key.into(),
            user_agent: user_agent.into(),
            agent: ureq::AgentBuilder::new().build(),
        }
    }

    pub fn send(&self, license_id: &str, fingerprint: &str) -> Result<HeartbeatResponse, HeartbeatError> {
        let body = HeartbeatRequest {
            license_id: license_id.to_string(),
            fingerprint: fingerprint.to_string(),
            verifier_version: self.user_agent.clone(),
            nonce: random_nonce_hex(),
            reported_at: Utc::now().to_rfc3339(),
        };
        let raw = serde_json::to_vec(&body).map_err(|e| HeartbeatError::Malformed(e.to_string()))?;
        let sig = hmac_hex(&self.api_key, &raw);
        let url = format!("{}/licenses/{}/heartbeat", self.base_url, license_id);

        let resp = self
            .agent
            .post(&url)
            .set("Content-Type", "application/json")
            .set("X-Forge-API-Key", &self.api_key)
            .set("X-Forge-Signature", &format!("sha256={sig}"))
            .set("User-Agent", &self.user_agent)
            .send_bytes(&raw);

        let resp = match resp {
            Ok(r) => r,
            Err(ureq::Error::Status(code, _)) => {
                return Err(match code {
                    401 => HeartbeatError::InvalidApiKey,
                    429 => HeartbeatError::RateLimited,
                    s if s >= 500 => HeartbeatError::ServerError(s),
                    s => HeartbeatError::ServerError(s),
                });
            }
            Err(e) => return Err(HeartbeatError::Transport(e.to_string())),
        };

        resp.into_json::<HeartbeatResponse>()
            .map_err(|e| HeartbeatError::Malformed(e.to_string()))
    }
}

pub(crate) fn hmac_hex(key: &str, body: &[u8]) -> String {
    let mut mac = HmacSha256::new_from_slice(key.as_bytes())
        .expect("HMAC accepts any key length");
    mac.update(body);
    hex::encode(mac.finalize().into_bytes())
}

fn random_nonce_hex() -> String {
    let mut b = [0u8; 16];
    rand::thread_rng().fill_bytes(&mut b);
    hex::encode(b)
}
