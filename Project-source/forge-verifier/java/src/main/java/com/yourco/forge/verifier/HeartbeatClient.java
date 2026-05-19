package com.yourco.forge.verifier;

import com.fasterxml.jackson.databind.ObjectMapper;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.time.Instant;
import java.util.HashMap;
import java.util.HexFormat;
import java.util.Map;

/**
 * Heartbeat client — periodically POSTs to {@code /api/v1/licenses/&#123;id&#125;/heartbeat}.
 *
 * <p>Wire protocol: HMAC-SHA256 of the JSON body using the API key as the secret,
 * delivered in the {@code X-Forge-Signature: sha256=&lt;hex&gt;} header. Matches
 * the Go / Python SDKs byte-for-byte.
 */
public final class HeartbeatClient {

    private static final ObjectMapper MAPPER = new ObjectMapper();
    private static final SecureRandom RNG = new SecureRandom();

    private final String baseUrl;
    private final String apiKey;
    private final String userAgent;
    private final HttpClient http;

    public HeartbeatClient(String baseUrl, String apiKey, String userAgent) {
        this(baseUrl, apiKey, userAgent, HttpClient.newHttpClient());
    }

    public HeartbeatClient(String baseUrl, String apiKey, String userAgent, HttpClient http) {
        this.baseUrl = baseUrl;
        this.apiKey = apiKey;
        this.userAgent = userAgent;
        this.http = http;
    }

    public Response send(String licenseId, String fingerprint) throws IOException, InterruptedException {
        Map<String, Object> body = new HashMap<>();
        body.put("license_id", licenseId);
        body.put("fingerprint", fingerprint);
        body.put("verifier_version", userAgent);
        body.put("nonce", randomNonceHex());
        body.put("reported_at", Instant.now().toString());

        byte[] raw = MAPPER.writeValueAsBytes(body);
        HttpRequest.Builder req = HttpRequest.newBuilder()
                .uri(URI.create(baseUrl + "/licenses/" + licenseId + "/heartbeat"))
                .header("Content-Type", "application/json")
                .header("X-Forge-API-Key", apiKey)
                .header("X-Forge-Signature", "sha256=" + hmacHex(apiKey, raw))
                .POST(HttpRequest.BodyPublishers.ofByteArray(raw));
        if (userAgent != null && !userAgent.isEmpty()) {
            req.header("User-Agent", userAgent);
        }
        HttpResponse<byte[]> resp = http.send(req.build(), HttpResponse.BodyHandlers.ofByteArray());
        int code = resp.statusCode();
        if (code == 401) throw new IOException("heartbeat: invalid api key (401)");
        if (code == 429) throw new IOException("heartbeat: rate limited (429)");
        if (code >= 500) throw new IOException("heartbeat: server error " + code);
        return MAPPER.readValue(resp.body(), Response.class);
    }

    private static String randomNonceHex() {
        byte[] b = new byte[16];
        RNG.nextBytes(b);
        return HexFormat.of().formatHex(b);
    }

    static String hmacHex(String key, byte[] body) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(key.getBytes(StandardCharsets.UTF_8), "HmacSHA256"));
            return HexFormat.of().formatHex(mac.doFinal(body));
        } catch (Exception e) {
            throw new IllegalStateException("HmacSHA256 unavailable", e);
        }
    }

    public static final class Response {
        public boolean ok;
        public String licenseStatus;
        public boolean multiEnvAnomaly;
        public int nextHeartbeatAfterSeconds;
        public String reason;
    }
}
