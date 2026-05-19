// SM2 verification — GM/T 0003.2-2012, the Chinese national cryptography standard.
//
// Wire format matches the Python reference SDK (forge-verifier/python):
//   - public key   = ASCII hex, 128 chars (uncompressed X || Y)
//   - signature    = ASCII hex (gmsm/sm2 `Verify` accepts ASN.1; we accept raw r||s hex)
//
// SM2 in Go is supplied by github.com/tjfoc/gmsm.

package forgeverifier

import (
	"crypto/elliptic"
	"encoding/hex"
	"fmt"
	"math/big"

	"github.com/tjfoc/gmsm/sm2"
)

// VerifySM2 checks a SM2 signature.
//
// publicKey is the ASCII-hex form of the uncompressed (X || Y) coordinates
// (128 chars) — matches the bytes stored in `.forge` payloads by the Python
// reference and by the LA's /public-keys endpoint.
//
// signature is the ASCII-hex form of the GM/T 0003.2 `r || s` byte string
// (length depends on integer sizes — typically 64 hex chars per coordinate).
//
// All inputs are byte slices because they come from the .forge tar entry as-is.
func verifySM2(payload, publicKeyBytes, signatureBytes []byte) (bool, error) {
	pubHex := string(publicKeyBytes)
	sigHex := string(signatureBytes)

	if len(pubHex) != 128 {
		return false, fmt.Errorf("sm2: public key must be 128 hex chars, got %d", len(pubHex))
	}
	xy, err := hex.DecodeString(pubHex)
	if err != nil {
		return false, fmt.Errorf("sm2: public key hex decode: %w", err)
	}
	pub := &sm2.PublicKey{
		Curve: sm2.P256Sm2(),
		X:     new(big.Int).SetBytes(xy[:32]),
		Y:     new(big.Int).SetBytes(xy[32:64]),
	}
	if !pub.Curve.IsOnCurve(pub.X, pub.Y) {
		return false, fmt.Errorf("sm2: public key not on SM2 curve")
	}

	sig, err := hex.DecodeString(sigHex)
	if err != nil {
		return false, fmt.Errorf("sm2: signature hex decode: %w", err)
	}
	if len(sig) < 32 {
		return false, fmt.Errorf("sm2: signature too short")
	}
	// gmsm's `Sm2Verify` expects raw r||s of equal halves; if signature is ASN.1
	// DER from another encoder, callers can wrap accordingly.
	half := len(sig) / 2
	r := new(big.Int).SetBytes(sig[:half])
	s := new(big.Int).SetBytes(sig[half:])
	// GM/T 0003 default user-id "1234567812345678" matches Python ref.
	return sm2.Sm2Verify(pub, payload, []byte(defaultSM2UserID), r, s), nil
}

const defaultSM2UserID = "1234567812345678"

// Ensure unused-import lint is happy if curve constants change.
var _ = elliptic.P256
