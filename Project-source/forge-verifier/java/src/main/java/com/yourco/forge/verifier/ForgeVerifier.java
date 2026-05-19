package com.yourco.forge.verifier;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import org.apache.commons.compress.archivers.tar.TarArchiveEntry;
import org.apache.commons.compress.archivers.tar.TarArchiveInputStream;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.GeneralSecurityException;
import java.security.KeyFactory;
import java.security.PublicKey;
import java.security.Signature;
import java.security.spec.X509EncodedKeySpec;
import java.time.Instant;
import java.util.Map;

/**
 * Forge License Authority Verifier — minimum viable Java SDK.
 *
 * <p>Supports Ed25519 signature verification + expiry check. RSA-PSS / SM2 / heartbeat /
 * binding documented in README; add when needed. Mirrors {@code forge-verifier (Go)}
 * MVP behavior so callers get consistent semantics across languages.
 */
public final class ForgeVerifier {

    public static final String FORGE_MAGIC = "forg";
    public static final String FORGE_VERSION = "1.0";

    private static final ObjectMapper MAPPER = new ObjectMapper().registerModule(new JavaTimeModule());

    /** Top-level entry: parse + verify. */
    public static Result verify(Path forgeFile, byte[] publicKey, Instant now) throws ForgeException {
        ForgeFile parsed = parse(forgeFile);
        return parsed.verify(publicKey, now);
    }

    /** Parse-only — use for CLI inspection without crypto. */
    public static ForgeFile parse(Path forgeFile) throws ForgeException {
        byte[] payloadRaw = null;
        byte[] signature = null;
        Metadata metadata = null;

        try (InputStream in = Files.newInputStream(forgeFile);
             TarArchiveInputStream tar = new TarArchiveInputStream(in)) {
            TarArchiveEntry entry;
            while ((entry = tar.getNextTarEntry()) != null) {
                byte[] buf = readEntry(tar);
                switch (entry.getName()) {
                    case "payload.json" -> payloadRaw = buf;
                    case "signature.bin" -> signature = buf;
                    case "metadata.json" -> metadata = MAPPER.readValue(buf, Metadata.class);
                    default -> { /* unknown entry — ignore for forward compat */ }
                }
            }
        } catch (IOException e) {
            throw new ForgeException("forge file malformed: " + e.getMessage(), Status.MALFORMED);
        }

        if (payloadRaw == null || signature == null || metadata == null) {
            throw new ForgeException("forge file missing required entry", Status.MALFORMED);
        }
        if (!FORGE_MAGIC.equals(metadata.magic)) {
            throw new ForgeException("bad magic: " + metadata.magic, Status.MALFORMED);
        }
        Payload payload;
        try {
            payload = MAPPER.readValue(payloadRaw, Payload.class);
        } catch (IOException e) {
            throw new ForgeException("payload.json malformed: " + e.getMessage(), Status.MALFORMED);
        }
        return new ForgeFile(payload, payloadRaw, signature, metadata);
    }

    private static byte[] readEntry(InputStream in) throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] buf = new byte[8192];
        int n;
        while ((n = in.read(buf)) > 0) {
            out.write(buf, 0, n);
        }
        return out.toByteArray();
    }

    public static final class ForgeFile {
        public final Payload payload;
        public final byte[] payloadRaw;
        public final byte[] signature;
        public final Metadata metadata;

        ForgeFile(Payload payload, byte[] payloadRaw, byte[] signature, Metadata metadata) {
            this.payload = payload;
            this.payloadRaw = payloadRaw;
            this.signature = signature;
            this.metadata = metadata;
        }

        public Result verify(byte[] publicKey, Instant now) throws ForgeException {
            Result.Builder r = new Result.Builder()
                    .status(Status.VALID)
                    .licenseId(payload.licenseId)
                    .expiresAt(payload.expiresAt)
                    .binding(payload.binding)
                    .fingerprintMustMatch(payload.boundFingerprint);

            switch (metadata.algorithm) {
                case "ed25519" -> verifyEd25519(publicKey);
                case "rsa2048", "rsa4096" -> verifyRsaPss(publicKey, metadata.algorithm);
                case "sm2" -> verifySm2(publicKey);
                default -> throw new ForgeException(
                        "algorithm unsupported: " + metadata.algorithm, Status.ALGORITHM_UNSUPPORTED);
            }

            if (!now.isBefore(payload.expiresAt)) {
                throw new ForgeException("license expired", r.status(Status.EXPIRED).build());
            }
            return r.build();
        }

        private void verifyRsaPss(byte[] derPublicKey, String algorithm) throws ForgeException {
            int expectedBits = "rsa4096".equals(algorithm) ? 4096 : 2048;
            try {
                KeyFactory kf = KeyFactory.getInstance("RSA");
                java.security.interfaces.RSAPublicKey pub =
                        (java.security.interfaces.RSAPublicKey)
                                kf.generatePublic(new X509EncodedKeySpec(derPublicKey));
                int bits = pub.getModulus().bitLength();
                if (bits != expectedBits) {
                    throw new ForgeException(
                            "rsa modulus is " + bits + " bits, expected " + expectedBits,
                            Status.SIGNATURE_INVALID);
                }
                Signature sig = Signature.getInstance("RSASSA-PSS");
                sig.setParameter(new java.security.spec.PSSParameterSpec(
                        "SHA-256", "MGF1",
                        java.security.spec.MGF1ParameterSpec.SHA256,
                        32, 1));
                sig.initVerify(pub);
                sig.update(payloadRaw);
                if (!sig.verify(signature)) {
                    throw new ForgeException("signature invalid", Status.SIGNATURE_INVALID);
                }
            } catch (GeneralSecurityException e) {
                throw new ForgeException(
                        "rsa-pss verify failure: " + e.getMessage(),
                        Status.SIGNATURE_INVALID);
            }
        }

        private void verifyEd25519(byte[] rawPublicKey) throws ForgeException {
            if (rawPublicKey.length != 32) {
                throw new ForgeException(
                        "ed25519 public key must be 32 bytes; got " + rawPublicKey.length,
                        Status.SIGNATURE_INVALID);
            }
            try {
                // JDK 15+ has native Ed25519. We assemble X.509 SubjectPublicKeyInfo on the fly.
                byte[] x509 = ed25519X509(rawPublicKey);
                KeyFactory kf = KeyFactory.getInstance("Ed25519");
                PublicKey pub = kf.generatePublic(new X509EncodedKeySpec(x509));

                Signature sig = Signature.getInstance("Ed25519");
                sig.initVerify(pub);
                sig.update(payloadRaw);
                if (!sig.verify(signature)) {
                    throw new ForgeException("signature invalid", Status.SIGNATURE_INVALID);
                }
            } catch (GeneralSecurityException e) {
                throw new ForgeException("ed25519 verify failure: " + e.getMessage(),
                        Status.SIGNATURE_INVALID);
            }
        }

        private void verifySm2(byte[] publicKeyAsciiHex) throws ForgeException {
            if (!Sm2Verifier.verify(payloadRaw, publicKeyAsciiHex, signature)) {
                throw new ForgeException("signature invalid", Status.SIGNATURE_INVALID);
            }
        }
    }

    /** Wrap raw 32-byte Ed25519 public key in the minimal X.509 SubjectPublicKeyInfo
     *  (so we can use the standard KeyFactory). */
    private static byte[] ed25519X509(byte[] raw) {
        // SEQUENCE { SEQUENCE { OID 1.3.101.112 } BIT STRING 0x00 || raw }
        byte[] prefix = new byte[]{
                0x30, 0x2a,
                0x30, 0x05, 0x06, 0x03, 0x2b, 0x65, 0x70,
                0x03, 0x21, 0x00,
        };
        byte[] out = new byte[prefix.length + raw.length];
        System.arraycopy(prefix, 0, out, 0, prefix.length);
        System.arraycopy(raw, 0, out, prefix.length, raw.length);
        return out;
    }

    public enum Status {
        VALID, EXPIRED, REVOKED, SIGNATURE_INVALID, ALGORITHM_UNSUPPORTED, MALFORMED
    }

    public static final class Metadata {
        public String magic;
        @com.fasterxml.jackson.annotation.JsonProperty("forge_version")
        public String forgeVersion;
        public String algorithm;
        @com.fasterxml.jackson.annotation.JsonProperty("key_id")
        public String keyId;
        @com.fasterxml.jackson.annotation.JsonProperty("signed_at")
        public Instant signedAt;
    }

    public static final class Payload {
        @com.fasterxml.jackson.annotation.JsonProperty("protocol_version")
        public String protocolVersion;
        @com.fasterxml.jackson.annotation.JsonProperty("license_id")
        public String licenseId;
        @com.fasterxml.jackson.annotation.JsonProperty("customer_id")
        public String customerId;
        @com.fasterxml.jackson.annotation.JsonProperty("product_id")
        public String productId;
        public String mode;
        public String scope;
        public String binding;
        @com.fasterxml.jackson.annotation.JsonProperty("bound_fingerprint")
        public String boundFingerprint;
        @com.fasterxml.jackson.annotation.JsonProperty("issued_at")
        public Instant issuedAt;
        @com.fasterxml.jackson.annotation.JsonProperty("expires_at")
        public Instant expiresAt;
        public Map<String, Object> features;
        public Map<String, Object> limits;
    }

    public static final class Result {
        public final Status status;
        public final String licenseId;
        public final Instant expiresAt;
        public final String binding;
        public final String fingerprintMustMatch;

        private Result(Builder b) {
            this.status = b.status;
            this.licenseId = b.licenseId;
            this.expiresAt = b.expiresAt;
            this.binding = b.binding;
            this.fingerprintMustMatch = b.fingerprintMustMatch;
        }

        public static final class Builder {
            private Status status;
            private String licenseId;
            private Instant expiresAt;
            private String binding;
            private String fingerprintMustMatch;
            public Builder status(Status s) { this.status = s; return this; }
            public Builder licenseId(String s) { this.licenseId = s; return this; }
            public Builder expiresAt(Instant s) { this.expiresAt = s; return this; }
            public Builder binding(String s) { this.binding = s; return this; }
            public Builder fingerprintMustMatch(String s) { this.fingerprintMustMatch = s; return this; }
            public Result build() { return new Result(this); }
        }
    }

    public static final class ForgeException extends Exception {
        public final Status status;
        public final Result result;
        public ForgeException(String msg, Status status) {
            super(msg);
            this.status = status;
            this.result = null;
        }
        public ForgeException(String msg, Result result) {
            super(msg);
            this.status = result.status;
            this.result = result;
        }
    }

    private ForgeVerifier() {}
}
