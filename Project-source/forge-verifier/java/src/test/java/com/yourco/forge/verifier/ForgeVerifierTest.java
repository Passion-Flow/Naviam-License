package com.yourco.forge.verifier;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.time.Instant;
import java.util.Base64;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ForgeVerifierTest {

    /** Same vector dir Python / Go also reads. */
    private static final Path VECTOR_ROOT =
            Paths.get("..", "spec", "test-vectors").toAbsolutePath().normalize();

    private static byte[] loadPublicKey(String vector) throws Exception {
        Path kpPath = VECTOR_ROOT.resolve(vector).resolve("keypair.json");
        JsonNode kp = new ObjectMapper().readTree(Files.readAllBytes(kpPath));
        return Base64.getDecoder().decode(kp.get("public_key_b64").asText());
    }

    private static Path forgeFile(String vector) {
        return VECTOR_ROOT.resolve(vector).resolve("expected.forge");
    }

    @Test
    void vector001_offlineNone() throws Exception {
        Path forge = forgeFile("001-ed25519-offline-none");
        byte[] pk = loadPublicKey("001-ed25519-offline-none");

        ForgeVerifier.Result r = ForgeVerifier.verify(forge, pk, Instant.parse("2026-06-01T00:00:00Z"));
        assertEquals(ForgeVerifier.Status.VALID, r.status);
        assertEquals("vector-001-ed25519-offline-none", r.licenseId);
        assertEquals("none", r.binding);
    }

    @Test
    void expired() throws Exception {
        Path forge = forgeFile("001-ed25519-offline-none");
        byte[] pk = loadPublicKey("001-ed25519-offline-none");

        ForgeVerifier.ForgeException ex = assertThrows(
                ForgeVerifier.ForgeException.class,
                () -> ForgeVerifier.verify(forge, pk, Instant.parse("2099-01-01T00:00:00Z"))
        );
        assertEquals(ForgeVerifier.Status.EXPIRED, ex.status);
    }

    @Test
    void vector004_sm2OfflineNone() throws Exception {
        Path forge = forgeFile("004-sm2-offline-none");
        byte[] pk = loadPublicKey("004-sm2-offline-none");

        ForgeVerifier.Result r = ForgeVerifier.verify(forge, pk, Instant.parse("2026-06-01T00:00:00Z"));
        assertEquals(ForgeVerifier.Status.VALID, r.status);
        assertEquals("vector-004-sm2-offline-none", r.licenseId);
    }

    @Test
    void tamperedSignature() throws Exception {
        Path forge = forgeFile("001-ed25519-offline-none");
        byte[] pk = loadPublicKey("001-ed25519-offline-none");

        ForgeVerifier.ForgeFile f = ForgeVerifier.parse(forge);
        assertNotNull(f);
        f.signature[0] ^= 0x01;
        ForgeVerifier.ForgeException ex = assertThrows(
                ForgeVerifier.ForgeException.class,
                () -> f.verify(pk, Instant.parse("2026-06-01T00:00:00Z"))
        );
        assertTrue(ex.status == ForgeVerifier.Status.SIGNATURE_INVALID,
                "want SIGNATURE_INVALID, got " + ex.status);
    }
}
