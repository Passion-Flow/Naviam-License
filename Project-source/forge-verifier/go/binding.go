// Soft binding fingerprint — see spec/binding-fingerprint.md for the canonical
// string + hash rules. Hard binding (TPM/SE) is platform-specific and left to callers.

package forgeverifier

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"net"
	"os"
	"runtime"
	"strings"
)

// ComputeSoftFingerprint builds `mac|hostname|cpu` per spec, SHA-256 → lowercase hex.
//
// Components that cannot be obtained (rare on supported platforms) substitute the
// literal "unknown" — never silently dropped, otherwise the hash becomes unstable.
func ComputeSoftFingerprint() (string, error) {
	mac, err := primaryMAC()
	if err != nil {
		mac = "unknown"
	}
	host, err := os.Hostname()
	if err != nil || host == "" {
		host = "unknown"
	}
	cpu := fmt.Sprintf("%s:%s:%d",
		safeOrUnknown(runtime.GOARCH),
		safeOrUnknown(runtime.GOOS),
		runtime.NumCPU(), // best-effort; CPU vendor/family/model needs cgo on darwin
	)

	canonical := fmt.Sprintf("%s|%s|%s",
		strings.ToLower(mac),
		strings.ToLower(host),
		cpu,
	)
	sum := sha256.Sum256([]byte(canonical))
	return hex.EncodeToString(sum[:]), nil
}

func primaryMAC() (string, error) {
	ifaces, err := net.Interfaces()
	if err != nil {
		return "", err
	}
	for _, ifc := range ifaces {
		if ifc.Flags&net.FlagLoopback != 0 || ifc.Flags&net.FlagUp == 0 {
			continue
		}
		// Skip virtual / docker / vmware interfaces — heuristic by name
		name := strings.ToLower(ifc.Name)
		if strings.Contains(name, "docker") || strings.Contains(name, "veth") ||
			strings.Contains(name, "vmnet") || strings.Contains(name, "br-") {
			continue
		}
		if len(ifc.HardwareAddr) >= 6 {
			return ifc.HardwareAddr.String(), nil
		}
	}
	return "", fmt.Errorf("no usable physical NIC")
}

func safeOrUnknown(s string) string {
	if s == "" {
		return "unknown"
	}
	return s
}
