// Online / hybrid composition — parses + verifies signature/expiry, then dispatches
// CRL refresh + heartbeat based on the license's own `mode` field.
//
// Fail-closed policy mirrors Go SDK (forge-verifier/go/online.go):
//   - offline → never touches network
//   - hybrid  → signature MUST pass; CRL + heartbeat best-effort; cached revoke still wins
//   - online  → all three MUST pass; network failure → reject

namespace YourCo.Forge.Verifier;

public sealed class OnlineVerifier
{
    private readonly byte[] _publicKey;
    private readonly HeartbeatClient? _heartbeat;
    private readonly CrlClient? _crl;

    public OnlineVerifier(byte[] publicKey, HeartbeatClient? heartbeat = null, CrlClient? crl = null)
    {
        _publicKey = publicKey;
        _heartbeat = heartbeat;
        _crl = crl;
    }

    public async Task<ForgeVerifier.Result> VerifyAsync(
        string forgePath,
        string fingerprint,
        DateTimeOffset now,
        CancellationToken ct = default)
    {
        var parsed = ForgeVerifier.Parse(forgePath);
        var res = parsed.Verify(_publicKey, now);
        var mode = string.IsNullOrEmpty(parsed.Payload.Mode) ? "offline" : parsed.Payload.Mode;

        switch (mode)
        {
            case "offline":
                return res;

            case "hybrid":
                if (_crl is not null)
                {
                    try { await _crl.RefreshAsync(ct).ConfigureAwait(false); }
                    catch { /* hybrid: ignore network errors; fall back to cached snapshot */ }
                    if (_crl.IsRevoked(parsed.Payload.LicenseId))
                    {
                        throw new ForgeVerifier.ForgeException("license revoked (CRL)",
                            new ForgeVerifier.Result
                            {
                                Status = ForgeVerifier.Status.Revoked,
                                LicenseId = parsed.Payload.LicenseId,
                                ExpiresAt = parsed.Payload.ExpiresAt,
                                Binding = parsed.Payload.Binding,
                                FingerprintMustMatch = parsed.Payload.BoundFingerprint,
                            });
                    }
                }
                if (_heartbeat is not null)
                {
                    try { await _heartbeat.SendAsync(parsed.Payload.LicenseId, fingerprint, ct).ConfigureAwait(false); }
                    catch { /* best-effort */ }
                }
                return res;

            case "online":
                if (_crl is null || _heartbeat is null)
                {
                    throw new ForgeVerifier.ForgeException(
                        "online mode requires CrlClient + HeartbeatClient",
                        ForgeVerifier.Status.Malformed);
                }
                try { await _crl.RefreshAsync(ct).ConfigureAwait(false); }
                catch (Exception e)
                {
                    throw new ForgeVerifier.ForgeException(
                        $"online: CRL refresh failed: {e.Message}",
                        ForgeVerifier.Status.SignatureInvalid);
                }
                if (_crl.IsRevoked(parsed.Payload.LicenseId))
                {
                    throw new ForgeVerifier.ForgeException("license revoked",
                        new ForgeVerifier.Result
                        {
                            Status = ForgeVerifier.Status.Revoked,
                            LicenseId = parsed.Payload.LicenseId,
                            ExpiresAt = parsed.Payload.ExpiresAt,
                            Binding = parsed.Payload.Binding,
                            FingerprintMustMatch = parsed.Payload.BoundFingerprint,
                        });
                }
                try
                {
                    var hb = await _heartbeat.SendAsync(parsed.Payload.LicenseId, fingerprint, ct)
                        .ConfigureAwait(false);
                    if (!string.IsNullOrEmpty(hb.LicenseStatus) && hb.LicenseStatus != "active")
                    {
                        throw new ForgeVerifier.ForgeException(
                            $"online: server reports license_status={hb.LicenseStatus}",
                            ForgeVerifier.Status.SignatureInvalid);
                    }
                }
                catch (ForgeVerifier.ForgeException) { throw; }
                catch (Exception e)
                {
                    throw new ForgeVerifier.ForgeException(
                        $"online: heartbeat failed: {e.Message}",
                        ForgeVerifier.Status.SignatureInvalid);
                }
                return res;

            default:
                throw new ForgeVerifier.ForgeException(
                    $"unknown license mode: {mode}",
                    ForgeVerifier.Status.Malformed);
        }
    }
}
