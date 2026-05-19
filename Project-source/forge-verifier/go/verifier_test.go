package forgeverifier

import (
	"encoding/base64"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
	"time"
)

// 测试向量目录（相对本包根）。Python SDK 也读同一套向量保证互操作。
const vectorRoot = "../spec/test-vectors"

type keypair struct {
	Algorithm string `json:"algorithm"`
	PublicKey string `json:"public_key_b64"`
}

func loadVector(t *testing.T, name string) (string, []byte) {
	t.Helper()
	dir := filepath.Join(vectorRoot, name)
	kpRaw, err := os.ReadFile(filepath.Join(dir, "keypair.json"))
	if err != nil {
		t.Fatalf("vector missing: %v", err)
	}
	var kp keypair
	if err := json.Unmarshal(kpRaw, &kp); err != nil {
		t.Fatalf("keypair: %v", err)
	}
	pk, err := base64.StdEncoding.DecodeString(kp.PublicKey)
	if err != nil {
		t.Fatalf("public_key_b64: %v", err)
	}
	return filepath.Join(dir, "expected.forge"), pk
}

func TestVector001_Ed25519_OfflineNone(t *testing.T) {
	path, pk := loadVector(t, "001-ed25519-offline-none")

	// expires_at = 2027-01-01 → use now well before
	now := time.Date(2026, 6, 1, 0, 0, 0, 0, time.UTC)
	res, err := Verify(path, pk, now)
	if err != nil {
		t.Fatalf("verify: %v", err)
	}
	if res.Status != "valid" {
		t.Fatalf("status=%q want valid", res.Status)
	}
	if res.LicenseID != "vector-001-ed25519-offline-none" {
		t.Fatalf("license_id=%q", res.LicenseID)
	}
	if res.Binding != "none" {
		t.Fatalf("binding=%q", res.Binding)
	}
}

func TestVector_Expired(t *testing.T) {
	path, pk := loadVector(t, "001-ed25519-offline-none")
	now := time.Date(2099, 1, 1, 0, 0, 0, 0, time.UTC)
	res, err := Verify(path, pk, now)
	if err != ErrExpired {
		t.Fatalf("want ErrExpired, got %v / res=%v", err, res)
	}
}

func TestVector004_SM2_OfflineNone(t *testing.T) {
	path, pk := loadVector(t, "004-sm2-offline-none")
	now := time.Date(2026, 6, 1, 0, 0, 0, 0, time.UTC)
	res, err := Verify(path, pk, now)
	if err != nil {
		t.Fatalf("verify SM2: %v", err)
	}
	if res.Status != "valid" {
		t.Fatalf("status=%q want valid", res.Status)
	}
	if res.LicenseID != "vector-004-sm2-offline-none" {
		t.Fatalf("license_id=%q", res.LicenseID)
	}
}

func TestVector_TamperedSignature(t *testing.T) {
	path, pk := loadVector(t, "001-ed25519-offline-none")
	f, err := Parse(path)
	if err != nil {
		t.Fatal(err)
	}
	// flip a bit in the signature
	f.Signature[0] ^= 0x01
	if _, err := f.Verify(pk, time.Date(2026, 6, 1, 0, 0, 0, 0, time.UTC)); err != ErrSignatureInvalid {
		t.Fatalf("want ErrSignatureInvalid, got %v", err)
	}
}
