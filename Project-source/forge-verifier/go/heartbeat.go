// Heartbeat client — POST /api/v1/licenses/{id}/heartbeat with HMAC-SHA256 body sig.
//
// Wire protocol matches forge-verifier/spec/verification-state-machine.md §Phase 4.

package forgeverifier

import (
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

// HeartbeatClient sends periodic check-ins to the LA.
type HeartbeatClient struct {
	BaseURL     string        // e.g. https://forge.your-co/api/v1
	APIKey      string        // X-Forge-API-Key plaintext
	HTTPClient  *http.Client  // nil → use http.DefaultClient
	UserAgent   string        // forwarded as `verifier_version` in body + UA header
}

// HeartbeatRequest body — matches forge-server schema.
type HeartbeatRequest struct {
	LicenseID       string `json:"license_id"`
	Fingerprint     string `json:"fingerprint"`
	VerifierVersion string `json:"verifier_version"`
	Nonce           string `json:"nonce"`
	ReportedAt      string `json:"reported_at"` // RFC 3339
}

// HeartbeatResponse body.
type HeartbeatResponse struct {
	OK                          bool   `json:"ok,omitempty"`
	LicenseStatus               string `json:"license_status"`
	MultiEnvAnomaly             bool   `json:"multi_env_anomaly"`
	NextHeartbeatAfterSeconds   int    `json:"next_heartbeat_after_seconds"`
	Reason                      string `json:"reason,omitempty"`
}

// Send POSTs one heartbeat. Caller picks fingerprint (usually ComputeSoftFingerprint()).
func (h *HeartbeatClient) Send(ctx context.Context, licenseID, fingerprint string) (*HeartbeatResponse, error) {
	body := HeartbeatRequest{
		LicenseID:       licenseID,
		Fingerprint:     fingerprint,
		VerifierVersion: h.UserAgent,
		Nonce:           hex.EncodeToString(randomBytes(16)),
		ReportedAt:      time.Now().UTC().Format(time.RFC3339),
	}
	raw, err := json.Marshal(body)
	if err != nil {
		return nil, err
	}
	url := fmt.Sprintf("%s/licenses/%s/heartbeat", h.BaseURL, licenseID)
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(raw))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Forge-API-Key", h.APIKey)
	req.Header.Set("X-Forge-Signature", "sha256="+hmacHex(h.APIKey, raw))
	if h.UserAgent != "" {
		req.Header.Set("User-Agent", h.UserAgent)
	}

	c := h.HTTPClient
	if c == nil {
		c = http.DefaultClient
	}
	resp, err := c.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode == 429 {
		return nil, fmt.Errorf("heartbeat: rate limited (429)")
	}
	if resp.StatusCode >= 500 {
		return nil, fmt.Errorf("heartbeat: server error %d", resp.StatusCode)
	}
	out := &HeartbeatResponse{}
	if err := json.NewDecoder(resp.Body).Decode(out); err != nil {
		return nil, err
	}
	if resp.StatusCode == 401 {
		return nil, fmt.Errorf("heartbeat: invalid api key (401)")
	}
	return out, nil
}

func hmacHex(key string, body []byte) string {
	mac := hmac.New(sha256.New, []byte(key))
	mac.Write(body)
	return hex.EncodeToString(mac.Sum(nil))
}

func randomBytes(n int) []byte {
	b := make([]byte, n)
	if _, err := io.ReadFull(rand.Reader, b); err != nil {
		// Should never happen on a working OS. Falling back to time-based
		// would weaken nonce uniqueness; better to panic loudly.
		panic("forge-verifier: crypto/rand unavailable: " + err.Error())
	}
	return b
}
