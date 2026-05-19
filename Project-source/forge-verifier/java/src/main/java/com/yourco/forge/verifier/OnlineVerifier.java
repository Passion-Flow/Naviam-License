package com.yourco.forge.verifier;

import com.yourco.forge.verifier.ForgeVerifier.ForgeException;
import com.yourco.forge.verifier.ForgeVerifier.ForgeFile;
import com.yourco.forge.verifier.ForgeVerifier.Result;
import com.yourco.forge.verifier.ForgeVerifier.Status;

import java.nio.file.Path;
import java.time.Instant;

/**
 * Composes {@link ForgeVerifier#verify}, {@link CrlClient} and {@link HeartbeatClient}
 * into one entry-point. The license's own {@code mode} field selects which network
 * calls run; callers don't need to know.
 *
 * <p>Fail-closed policy:
 * <ul>
 *   <li>{@code offline} — only signature + expiry; never touches the network.</li>
 *   <li>{@code hybrid} — signature + expiry MUST pass; CRL + heartbeat best-effort.
 *       Network failure does not invalidate; an entry in the cached CRL does.</li>
 *   <li>{@code online} — signature + expiry MUST pass AND heartbeat MUST succeed AND
 *       license MUST NOT be in CRL. Network failure → reject.</li>
 * </ul>
 */
public final class OnlineVerifier {

    private final byte[] publicKey;
    private final HeartbeatClient heartbeat;
    private final CrlClient crl;

    public OnlineVerifier(byte[] publicKey, HeartbeatClient heartbeat, CrlClient crl) {
        this.publicKey = publicKey;
        this.heartbeat = heartbeat;
        this.crl = crl;
    }

    public Result verify(Path forgeFile, String fingerprint, Instant now) throws ForgeException {
        ForgeFile parsed = ForgeVerifier.parse(forgeFile);
        Result res = parsed.verify(publicKey, now);
        String mode = parsed.payload.mode == null ? "offline" : parsed.payload.mode;
        switch (mode) {
            case "offline":
            case "":
                return res;

            case "hybrid":
                if (crl != null) {
                    try {
                        crl.refresh();
                    } catch (Exception ignored) {
                        // hybrid is best-effort on network — fall back to cached snapshot
                    }
                    if (crl.isRevoked(parsed.payload.licenseId)) {
                        throw new ForgeException("license revoked (CRL)",
                                new Result.Builder().status(Status.REVOKED)
                                        .licenseId(parsed.payload.licenseId)
                                        .expiresAt(parsed.payload.expiresAt)
                                        .binding(parsed.payload.binding)
                                        .fingerprintMustMatch(parsed.payload.boundFingerprint)
                                        .build());
                    }
                }
                if (heartbeat != null) {
                    try {
                        heartbeat.send(parsed.payload.licenseId, fingerprint);
                    } catch (Exception ignored) {
                        // hybrid heartbeat is best-effort
                    }
                }
                return res;

            case "online":
                if (crl == null || heartbeat == null) {
                    throw new ForgeException("online mode requires CrlClient + HeartbeatClient",
                            Status.MALFORMED);
                }
                try {
                    crl.refresh();
                } catch (Exception e) {
                    throw new ForgeException("online: CRL refresh failed: " + e.getMessage(),
                            Status.SIGNATURE_INVALID);
                }
                if (crl.isRevoked(parsed.payload.licenseId)) {
                    throw new ForgeException("license revoked",
                            new Result.Builder().status(Status.REVOKED)
                                    .licenseId(parsed.payload.licenseId)
                                    .expiresAt(parsed.payload.expiresAt)
                                    .binding(parsed.payload.binding)
                                    .fingerprintMustMatch(parsed.payload.boundFingerprint)
                                    .build());
                }
                try {
                    HeartbeatClient.Response hb =
                            heartbeat.send(parsed.payload.licenseId, fingerprint);
                    if (hb.licenseStatus != null && !hb.licenseStatus.isEmpty()
                            && !"active".equals(hb.licenseStatus)) {
                        throw new ForgeException(
                                "online: server reports license_status=" + hb.licenseStatus,
                                Status.SIGNATURE_INVALID);
                    }
                } catch (ForgeException fe) {
                    throw fe;
                } catch (Exception e) {
                    throw new ForgeException("online: heartbeat failed: " + e.getMessage(),
                            Status.SIGNATURE_INVALID);
                }
                return res;

            default:
                throw new ForgeException("unknown license mode: " + mode, Status.MALFORMED);
        }
    }
}
