//! CRL client — fetches and caches `GET /api/v1/revocation-list`.
//!
//! Honors `ETag` / `If-None-Match`. On 304 we keep the existing snapshot. Thread-safe;
//! one instance per process is enough.

use std::collections::HashSet;
use std::sync::RwLock;
use std::time::SystemTime;

use serde::Deserialize;
use thiserror::Error;

#[derive(Debug, Error)]
pub enum CrlError {
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

#[derive(Debug, Deserialize)]
struct CrlBody {
    #[serde(default)]
    license_ids: Vec<String>,
    #[serde(default)]
    #[allow(dead_code)]
    generated_at: Option<String>,
}

pub struct CrlClient {
    pub base_url: String,
    pub api_key: String,
    pub user_agent: String,
    agent: ureq::Agent,
    state: RwLock<State>,
}

struct State {
    revoked: HashSet<String>,
    etag: String,
    last_fetched: Option<SystemTime>,
}

impl CrlClient {
    pub fn new(base_url: impl Into<String>, api_key: impl Into<String>, user_agent: impl Into<String>) -> Self {
        Self {
            base_url: base_url.into(),
            api_key: api_key.into(),
            user_agent: user_agent.into(),
            agent: ureq::AgentBuilder::new().build(),
            state: RwLock::new(State {
                revoked: HashSet::new(),
                etag: String::new(),
                last_fetched: None,
            }),
        }
    }

    pub fn refresh(&self) -> Result<(), CrlError> {
        let url = format!("{}/revocation-list", self.base_url);
        let mut req = self
            .agent
            .get(&url)
            .set("Accept", "application/json")
            .set("User-Agent", &self.user_agent);
        if !self.api_key.is_empty() {
            req = req.set("X-Forge-API-Key", &self.api_key);
        }
        {
            let s = self.state.read().unwrap();
            if !s.etag.is_empty() {
                req = req.set("If-None-Match", &s.etag);
            }
        }

        let resp = match req.call() {
            Ok(r) => r,
            Err(ureq::Error::Status(304, _)) => {
                self.state.write().unwrap().last_fetched = Some(SystemTime::now());
                return Ok(());
            }
            Err(ureq::Error::Status(code, _)) => {
                return Err(match code {
                    401 => CrlError::InvalidApiKey,
                    429 => CrlError::RateLimited,
                    s if s >= 500 => CrlError::ServerError(s),
                    s => CrlError::ServerError(s),
                });
            }
            Err(e) => return Err(CrlError::Transport(e.to_string())),
        };
        let etag = resp.header("etag").unwrap_or("").to_string();
        let body: CrlBody = resp
            .into_json()
            .map_err(|e| CrlError::Malformed(e.to_string()))?;
        let next: HashSet<String> = body.license_ids.into_iter().collect();

        let mut s = self.state.write().unwrap();
        s.revoked = next;
        s.etag = etag;
        s.last_fetched = Some(SystemTime::now());
        Ok(())
    }

    pub fn is_revoked(&self, license_id: &str) -> bool {
        self.state.read().unwrap().revoked.contains(license_id)
    }

    pub fn size(&self) -> usize {
        self.state.read().unwrap().revoked.len()
    }

    pub fn last_fetched(&self) -> Option<SystemTime> {
        self.state.read().unwrap().last_fetched
    }
}
