//! Online / hybrid composition — parses + verifies signature/expiry, then dispatches
//! CRL refresh + heartbeat based on the license's own `mode` field.
//!
//! Fail-closed policy mirrors the Go / Java / C# SDKs:
//!   - `offline` → never touches network
//!   - `hybrid`  → signature MUST pass; CRL + heartbeat best-effort; cached revoke wins
//!   - `online`  → all three MUST pass; network failure → reject

use std::path::Path;

use chrono::{DateTime, Utc};

use crate::crl::CrlClient;
use crate::heartbeat::HeartbeatClient;
use crate::{parse, ForgeError, Status, VerifyResult};

pub struct OnlineVerifier<'a> {
    pub public_key: &'a [u8],
    pub heartbeat: Option<&'a HeartbeatClient>,
    pub crl: Option<&'a CrlClient>,
}

impl<'a> OnlineVerifier<'a> {
    pub fn verify(
        &self,
        path: impl AsRef<Path>,
        fingerprint: &str,
        now: DateTime<Utc>,
    ) -> Result<VerifyResult, ForgeError> {
        let parsed = parse(path)?;
        let res = parsed.verify(self.public_key, now)?;
        let license_id = parsed.payload.license_id.clone();
        let mode = parsed.payload.mode.as_str();

        match mode {
            "offline" | "" => Ok(res),

            "hybrid" => {
                if let Some(crl) = self.crl {
                    let _ = crl.refresh(); // best-effort
                    if crl.is_revoked(&license_id) {
                        let mut r = res.clone();
                        r.status = Status::Revoked;
                        return Err(ForgeError::Revoked { license_id, result: r });
                    }
                }
                if let Some(hb) = self.heartbeat {
                    let _ = hb.send(&license_id, fingerprint); // best-effort
                }
                Ok(res)
            }

            "online" => {
                let crl = self.crl.ok_or(ForgeError::OnlineRequiresClients)?;
                let hb = self.heartbeat.ok_or(ForgeError::OnlineRequiresClients)?;
                crl.refresh()
                    .map_err(|e| ForgeError::OnlineFailed(format!("CRL refresh: {e}")))?;
                if crl.is_revoked(&license_id) {
                    let mut r = res.clone();
                    r.status = Status::Revoked;
                    return Err(ForgeError::Revoked { license_id, result: r });
                }
                let hb_resp = hb
                    .send(&license_id, fingerprint)
                    .map_err(|e| ForgeError::OnlineFailed(format!("heartbeat: {e}")))?;
                if !hb_resp.license_status.is_empty() && hb_resp.license_status != "active" {
                    return Err(ForgeError::OnlineFailed(format!(
                        "server reports license_status={}",
                        hb_resp.license_status
                    )));
                }
                Ok(res)
            }

            other => Err(ForgeError::UnknownMode(other.to_string())),
        }
    }
}
