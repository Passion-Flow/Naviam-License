//! Soft fingerprint — best-effort host identifier for `binding=fingerprint-soft`.
//!
//! Canonical string: `mac|hostname|cpu` (lowercased), SHA-256 → lowercase hex.
//! Matches the Go / Python / Java / C# SDKs byte-for-byte.

use sha2::{Digest, Sha256};

/// Compute the soft fingerprint for the current host.
///
/// Returns `(hex, canonical)` — the second value is the pre-hash string,
/// useful for debugging when two hosts hash to different values.
pub fn compute_soft_fingerprint() -> String {
    let mac = safe(&primary_mac());
    let hostname = safe(
        &hostname::get()
            .ok()
            .and_then(|s| s.into_string().ok())
            .unwrap_or_default(),
    );
    let cpu = safe(&cpu_description());

    let canonical = format!("{mac}|{hostname}|{cpu}").to_lowercase();
    let mut hasher = Sha256::new();
    hasher.update(canonical.as_bytes());
    hex::encode(hasher.finalize())
}

fn primary_mac() -> String {
    match mac_address::get_mac_address() {
        Ok(Some(addr)) => addr.to_string().to_lowercase(),
        _ => String::new(),
    }
}

fn cpu_description() -> String {
    format!(
        "{}:{}:{}",
        std::env::consts::ARCH,
        std::env::consts::OS,
        num_cpus::get()
    )
}

fn safe(s: &str) -> String {
    if s.is_empty() {
        "unknown".to_string()
    } else {
        s.to_string()
    }
}
