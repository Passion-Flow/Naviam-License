//! SM2 (GM/T 0003.2-2012) verification via the `libsm` pure-Rust crate.
//!
//! Wire format matches the Python reference SDK:
//!   - public key   = ASCII hex, 128 chars (uncompressed X || Y)
//!   - signature    = ASCII hex of GM/T raw `r || s`
//!
//! GM/T 0003 default user-id `"1234567812345678"` (also the Python default).

use libsm::sm2::signature::{SigCtx, Signature};

pub(crate) fn verify(payload: &[u8], public_key_ascii_hex: &[u8], signature_ascii_hex: &[u8]) -> bool {
    if public_key_ascii_hex.len() != 128 {
        return false;
    }
    let pub_hex = match std::str::from_utf8(public_key_ascii_hex) {
        Ok(s) => s,
        Err(_) => return false,
    };
    let xy = match hex::decode(pub_hex) {
        Ok(b) if b.len() == 64 => b,
        _ => return false,
    };
    // libsm accepts uncompressed SEC1 form (0x04 || X || Y).
    let mut sec1 = Vec::with_capacity(65);
    sec1.push(0x04);
    sec1.extend_from_slice(&xy);

    let ctx = SigCtx::new();
    let pk = match ctx.load_pubkey(&sec1) {
        Ok(p) => p,
        Err(_) => return false,
    };

    let sig_hex = match std::str::from_utf8(signature_ascii_hex) {
        Ok(s) => s,
        Err(_) => return false,
    };
    let sig_bytes = match hex::decode(sig_hex) {
        Ok(b) if b.len() >= 32 && b.len() % 2 == 0 => b,
        _ => return false,
    };
    let half = sig_bytes.len() / 2;
    let sig = Signature::new(&sig_bytes[..half], &sig_bytes[half..]);

    ctx.verify(payload, &pk, &sig).unwrap_or(false)
}
