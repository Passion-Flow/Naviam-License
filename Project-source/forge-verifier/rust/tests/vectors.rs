use base64::Engine;
use chrono::{TimeZone, Utc};
use forge_verifier::{parse, verify, ForgeError, Status};
use std::path::PathBuf;

// 共享测试向量目录
fn vector_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("spec")
        .join("test-vectors")
}

fn load_public_key(vector: &str) -> Vec<u8> {
    let path = vector_root().join(vector).join("keypair.json");
    let raw = std::fs::read(&path).expect("vector keypair");
    let v: serde_json::Value = serde_json::from_slice(&raw).unwrap();
    let b64 = v["public_key_b64"].as_str().unwrap();
    base64::engine::general_purpose::STANDARD.decode(b64).unwrap()
}

fn forge_file(vector: &str) -> PathBuf {
    vector_root().join(vector).join("expected.forge")
}

#[test]
fn vector_001_offline_none() {
    let pk = load_public_key("001-ed25519-offline-none");
    let now = Utc.with_ymd_and_hms(2026, 6, 1, 0, 0, 0).unwrap();
    let r = verify(forge_file("001-ed25519-offline-none"), &pk, now).expect("verify");
    assert_eq!(r.status, Status::Valid);
    assert_eq!(r.license_id, "vector-001-ed25519-offline-none");
    assert_eq!(r.binding, "none");
}

#[test]
fn expired_clock() {
    let pk = load_public_key("001-ed25519-offline-none");
    let now = Utc.with_ymd_and_hms(2099, 1, 1, 0, 0, 0).unwrap();
    let err = verify(forge_file("001-ed25519-offline-none"), &pk, now).unwrap_err();
    match err {
        ForgeError::Expired { result, .. } => assert_eq!(result.status, Status::Expired),
        other => panic!("want Expired, got {other:?}"),
    }
}

#[test]
fn tampered_signature() {
    let pk = load_public_key("001-ed25519-offline-none");
    let mut f = parse(forge_file("001-ed25519-offline-none")).unwrap();
    f.signature[0] ^= 0x01;
    let err = f
        .verify(&pk, Utc.with_ymd_and_hms(2026, 6, 1, 0, 0, 0).unwrap())
        .unwrap_err();
    matches!(err, ForgeError::SignatureInvalid);
}

#[test]
fn vector_004_sm2_offline_none() {
    let pk = load_public_key("004-sm2-offline-none");
    let now = Utc.with_ymd_and_hms(2026, 6, 1, 0, 0, 0).unwrap();
    let r = verify(forge_file("004-sm2-offline-none"), &pk, now).expect("verify SM2");
    assert_eq!(r.status, Status::Valid);
    assert_eq!(r.license_id, "vector-004-sm2-offline-none");
}
