// Online / hybrid verifier — composes Verify + CRL + Heartbeat into one entry-point.
//
// Fail-closed policy:
//   - mode=offline    → only signature + expiry; never touches the network
//   - mode=hybrid     → signature + expiry MUST pass; CRL + heartbeat best-effort
//                       (network failure does NOT invalidate; revocation does)
//   - mode=online     → signature + expiry MUST pass AND heartbeat MUST succeed AND
//                       license MUST NOT be in CRL. Network failure → invalid.

package forgeverifier

import (
	"context"
	"errors"
	"fmt"
	"time"
)

// OnlineVerifier holds the network clients needed for hybrid / online modes.
//
// Reuse a single instance across verifications — both clients are safe for
// concurrent use and cache state internally (CRL ETag, etc.).
type OnlineVerifier struct {
	PublicKey []byte
	Heartbeat *HeartbeatClient
	CRL       *CRLClient
}

// Verify performs the full verification flow against `path`. The license's own
// `mode` field decides which network calls run; callers don't need to know.
//
// Returns the verification result and a non-nil error iff the license should be
// rejected by the caller.
func (v *OnlineVerifier) Verify(ctx context.Context, path, fingerprint string, now time.Time) (*Result, error) {
	f, err := Parse(path)
	if err != nil {
		return nil, err
	}
	res, err := f.Verify(v.PublicKey, now)
	if err != nil {
		return res, err
	}

	switch f.Payload.Mode {
	case "offline", "":
		return res, nil

	case "hybrid":
		if v.CRL != nil {
			if refreshErr := v.CRL.Refresh(ctx); refreshErr == nil {
				if v.CRL.IsRevoked(f.Payload.LicenseID) {
					res.Status = "revoked"
					return res, fmt.Errorf("license revoked (CRL)")
				}
			}
			// network error → keep going on cached snapshot
			if v.CRL.IsRevoked(f.Payload.LicenseID) {
				res.Status = "revoked"
				return res, fmt.Errorf("license revoked (cached CRL)")
			}
		}
		if v.Heartbeat != nil {
			_, _ = v.Heartbeat.Send(ctx, f.Payload.LicenseID, fingerprint)
			// hybrid is best-effort on heartbeat; ignore network errors
		}
		return res, nil

	case "online":
		if v.CRL == nil || v.Heartbeat == nil {
			return res, errors.New("online mode requires CRL + Heartbeat clients")
		}
		if err := v.CRL.Refresh(ctx); err != nil {
			return res, fmt.Errorf("online: CRL refresh failed: %w", err)
		}
		if v.CRL.IsRevoked(f.Payload.LicenseID) {
			res.Status = "revoked"
			return res, fmt.Errorf("license revoked")
		}
		hb, err := v.Heartbeat.Send(ctx, f.Payload.LicenseID, fingerprint)
		if err != nil {
			return res, fmt.Errorf("online: heartbeat failed: %w", err)
		}
		if hb.LicenseStatus != "" && hb.LicenseStatus != "active" {
			res.Status = hb.LicenseStatus
			return res, fmt.Errorf("online: server reports license_status=%s", hb.LicenseStatus)
		}
		return res, nil

	default:
		return res, fmt.Errorf("unknown license mode: %q", f.Payload.Mode)
	}
}
