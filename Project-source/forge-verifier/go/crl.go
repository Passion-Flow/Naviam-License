// CRL (Certificate Revocation List) client — pulls the LA's revocation snapshot
// and answers "is this license_id revoked right now?".
//
// Wire protocol matches forge-server `GET /api/v1/revocation-list`:
//   - response: {"license_ids": ["...", "..."], "generated_at": "RFC3339"}
//   - supports HTTP caching via If-None-Match / ETag (304 → keep current set)

package forgeverifier

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"sync"
	"time"
)

// CRLClient fetches and caches the revocation list.
//
// Reuse a single client across Verify calls; it holds the in-memory set and
// the last ETag. Safe for concurrent use.
type CRLClient struct {
	BaseURL    string        // e.g. https://forge.your-co/api/v1
	APIKey     string        // X-Forge-API-Key
	HTTPClient *http.Client  // nil → http.DefaultClient
	UserAgent  string

	mu          sync.RWMutex
	revoked     map[string]struct{}
	etag        string
	lastFetched time.Time
}

// CRLResponse mirrors forge-server's response shape.
type CRLResponse struct {
	LicenseIDs  []string `json:"license_ids"`
	GeneratedAt string   `json:"generated_at"`
}

// Refresh re-fetches the CRL. On 304 it keeps the existing snapshot. On 5xx
// or network failure it returns the error and leaves the snapshot alone — the
// caller decides whether stale data is acceptable (hybrid mode usually says yes).
func (c *CRLClient) Refresh(ctx context.Context) error {
	url := fmt.Sprintf("%s/revocation-list", c.BaseURL)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return err
	}
	req.Header.Set("Accept", "application/json")
	if c.APIKey != "" {
		req.Header.Set("X-Forge-API-Key", c.APIKey)
	}
	if c.UserAgent != "" {
		req.Header.Set("User-Agent", c.UserAgent)
	}
	c.mu.RLock()
	if c.etag != "" {
		req.Header.Set("If-None-Match", c.etag)
	}
	c.mu.RUnlock()

	client := c.HTTPClient
	if client == nil {
		client = http.DefaultClient
	}
	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	switch resp.StatusCode {
	case http.StatusNotModified:
		c.mu.Lock()
		c.lastFetched = time.Now()
		c.mu.Unlock()
		return nil
	case http.StatusOK:
		// fall through
	case http.StatusUnauthorized:
		return fmt.Errorf("crl: invalid api key (401)")
	case http.StatusTooManyRequests:
		return fmt.Errorf("crl: rate limited (429)")
	default:
		if resp.StatusCode >= 500 {
			return fmt.Errorf("crl: server error %d", resp.StatusCode)
		}
		return fmt.Errorf("crl: unexpected status %d", resp.StatusCode)
	}

	body := &CRLResponse{}
	if err := json.NewDecoder(resp.Body).Decode(body); err != nil {
		return fmt.Errorf("crl: decode: %w", err)
	}
	set := make(map[string]struct{}, len(body.LicenseIDs))
	for _, id := range body.LicenseIDs {
		set[id] = struct{}{}
	}

	c.mu.Lock()
	c.revoked = set
	c.etag = resp.Header.Get("ETag")
	c.lastFetched = time.Now()
	c.mu.Unlock()
	return nil
}

// IsRevoked returns true if the license_id is in the cached revocation set.
// Returns false if Refresh has never succeeded — callers in "online" mode
// should call Refresh first and fail closed on its error.
func (c *CRLClient) IsRevoked(licenseID string) bool {
	c.mu.RLock()
	defer c.mu.RUnlock()
	if c.revoked == nil {
		return false
	}
	_, ok := c.revoked[licenseID]
	return ok
}

// LastFetched reports when the last successful network call completed (304 counts).
// Zero time means we never got a successful response.
func (c *CRLClient) LastFetched() time.Time {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return c.lastFetched
}

// Size returns the number of revoked IDs currently cached.
func (c *CRLClient) Size() int {
	c.mu.RLock()
	defer c.mu.RUnlock()
	return len(c.revoked)
}
