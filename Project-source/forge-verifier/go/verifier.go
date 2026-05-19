// Package forgeverifier — Forge License Authority Verifier for Go.
//
// Minimum viable subset (matches Python SDK behavior for offline + none binding):
//   - parse .forge tarball → payload.json + signature.bin + metadata.json
//   - verify Ed25519 signature (RSA / SM2 documented in TODOs; add when needed)
//   - check expires_at
//
// Heartbeat / binding / CRL — left to callers (or future iterations). See README.
package forgeverifier

import (
	"archive/tar"
	"crypto"
	"crypto/ed25519"
	"crypto/rsa"
	"crypto/sha256"
	"crypto/x509"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"time"
)

// ForgeMagic identifies a Forge license container.
const ForgeMagic = "forg"

// ForgeVersion is the wire format we understand.
const ForgeVersion = "1.0"

// Metadata is the small header packed alongside the signature.
type Metadata struct {
	Magic        string    `json:"magic"`
	ForgeVersion string    `json:"forge_version"`
	Algorithm    string    `json:"algorithm"`
	KeyID        string    `json:"key_id"`
	SignedAt     time.Time `json:"signed_at"`
}

// Payload mirrors the canonical payload.json structure.
// We unmarshal into a struct for typed access but the *raw bytes* of
// payload.json are what gets signed — keep them around.
type Payload struct {
	ProtocolVersion string                 `json:"protocol_version"`
	LicenseID       string                 `json:"license_id"`
	CustomerID      string                 `json:"customer_id"`
	ProductID       string                 `json:"product_id"`
	Mode            string                 `json:"mode"`
	Scope           string                 `json:"scope"`
	Binding         string                 `json:"binding"`
	BoundFingerprint *string               `json:"bound_fingerprint,omitempty"`
	IssuedAt        time.Time              `json:"issued_at"`
	ExpiresAt       time.Time              `json:"expires_at"`
	Features        map[string]interface{} `json:"features"`
	Limits          map[string]interface{} `json:"limits"`
}

// File is the parsed-but-not-yet-verified .forge container.
type File struct {
	Payload     Payload
	PayloadRaw  []byte // exact bytes signed
	Signature   []byte
	Metadata    Metadata
}

// Result is the verification outcome — mirrors expected-verify.json in test vectors.
type Result struct {
	Status               string  `json:"status"`                 // "valid" / "expired" / ...
	LicenseID            string  `json:"license_id"`
	ExpiresAt            string  `json:"expires_at"`
	Binding              string  `json:"binding"`
	FingerprintMustMatch *string `json:"fingerprint_must_match"`
}

// Sentinel errors.
var (
	ErrForgeFileMalformed = errors.New("forge file malformed")
	ErrAlgorithmUnsupported = errors.New("algorithm unsupported by this SDK")
	ErrSignatureInvalid    = errors.New("signature invalid")
	ErrExpired             = errors.New("license expired")
)

// Verify reads a .forge file from disk and verifies it with the given public key.
// publicKey encoding depends on algorithm:
//   - ed25519: 32-byte raw key
func Verify(path string, publicKey []byte, now time.Time) (*Result, error) {
	f, err := Parse(path)
	if err != nil {
		return nil, err
	}
	return f.Verify(publicKey, now)
}

// Parse extracts the three tar entries; does no crypto.
func Parse(path string) (*File, error) {
	fh, err := os.Open(path)
	if err != nil {
		return nil, fmt.Errorf("%w: %v", ErrForgeFileMalformed, err)
	}
	defer fh.Close()

	out := &File{}
	tr := tar.NewReader(fh)
	for {
		hdr, err := tr.Next()
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			return nil, fmt.Errorf("%w: tar read: %v", ErrForgeFileMalformed, err)
		}
		buf, err := io.ReadAll(tr)
		if err != nil {
			return nil, fmt.Errorf("%w: entry read: %v", ErrForgeFileMalformed, err)
		}
		switch hdr.Name {
		case "payload.json":
			out.PayloadRaw = buf
			if err := json.Unmarshal(buf, &out.Payload); err != nil {
				return nil, fmt.Errorf("%w: payload.json: %v", ErrForgeFileMalformed, err)
			}
		case "signature.bin":
			out.Signature = buf
		case "metadata.json":
			if err := json.Unmarshal(buf, &out.Metadata); err != nil {
				return nil, fmt.Errorf("%w: metadata.json: %v", ErrForgeFileMalformed, err)
			}
		}
	}

	if out.PayloadRaw == nil || out.Signature == nil || out.Metadata.Magic == "" {
		return nil, fmt.Errorf("%w: missing entry", ErrForgeFileMalformed)
	}
	if out.Metadata.Magic != ForgeMagic {
		return nil, fmt.Errorf("%w: bad magic %q", ErrForgeFileMalformed, out.Metadata.Magic)
	}
	return out, nil
}

// Verify performs crypto + temporal checks. Returns a typed result + error.
func (f *File) Verify(publicKey []byte, now time.Time) (*Result, error) {
	res := &Result{
		Status:               "valid",
		LicenseID:            f.Payload.LicenseID,
		ExpiresAt:            f.Payload.ExpiresAt.Format(time.RFC3339),
		Binding:              f.Payload.Binding,
		FingerprintMustMatch: f.Payload.BoundFingerprint,
	}

	switch f.Metadata.Algorithm {
	case "ed25519":
		if len(publicKey) != ed25519.PublicKeySize {
			return nil, fmt.Errorf("%w: ed25519 public key must be %d bytes, got %d",
				ErrSignatureInvalid, ed25519.PublicKeySize, len(publicKey))
		}
		if !ed25519.Verify(ed25519.PublicKey(publicKey), f.PayloadRaw, f.Signature) {
			res.Status = "signature_invalid"
			return res, ErrSignatureInvalid
		}
	case "rsa2048", "rsa4096":
		// public_key is DER-encoded SubjectPublicKeyInfo (see spec/algorithm-encoding.md).
		pubAny, err := x509.ParsePKIXPublicKey(publicKey)
		if err != nil {
			return nil, fmt.Errorf("%w: rsa public key parse: %v", ErrSignatureInvalid, err)
		}
		rsaPub, ok := pubAny.(*rsa.PublicKey)
		if !ok {
			return nil, fmt.Errorf("%w: rsa public key is not an RSA key", ErrSignatureInvalid)
		}
		bitLen := rsaPub.N.BitLen()
		expected := 2048
		if f.Metadata.Algorithm == "rsa4096" {
			expected = 4096
		}
		if bitLen != expected {
			return nil, fmt.Errorf("%w: rsa modulus is %d bits, expected %d",
				ErrSignatureInvalid, bitLen, expected)
		}
		// RSA-PSS-SHA256, salt length = hash length (32 B)
		hashed := sha256.Sum256(f.PayloadRaw)
		opts := &rsa.PSSOptions{SaltLength: 32, Hash: crypto.SHA256}
		if err := rsa.VerifyPSS(rsaPub, crypto.SHA256, hashed[:], f.Signature, opts); err != nil {
			res.Status = "signature_invalid"
			return res, ErrSignatureInvalid
		}
	case "sm2":
		ok, err := verifySM2(f.PayloadRaw, publicKey, f.Signature)
		if err != nil {
			return nil, fmt.Errorf("%w: %v", ErrSignatureInvalid, err)
		}
		if !ok {
			res.Status = "signature_invalid"
			return res, ErrSignatureInvalid
		}
	default:
		return nil, fmt.Errorf("%w: %s", ErrAlgorithmUnsupported, f.Metadata.Algorithm)
	}

	if !now.Before(f.Payload.ExpiresAt) {
		res.Status = "expired"
		return res, ErrExpired
	}

	return res, nil
}
