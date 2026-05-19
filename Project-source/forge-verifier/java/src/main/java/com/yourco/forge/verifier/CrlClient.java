package com.yourco.forge.verifier;

import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Instant;
import java.util.HashSet;
import java.util.Set;
import java.util.concurrent.locks.ReentrantReadWriteLock;

/**
 * CRL client — fetches and caches {@code GET /api/v1/revocation-list}.
 *
 * <p>Honors {@code ETag} / {@code If-None-Match}: on 304 we keep the existing
 * snapshot. Thread-safe; reuse a single instance across verify calls.
 */
public final class CrlClient {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    private final String baseUrl;
    private final String apiKey;
    private final String userAgent;
    private final HttpClient http;

    private final ReentrantReadWriteLock lock = new ReentrantReadWriteLock();
    private Set<String> revoked = new HashSet<>();
    private String etag = "";
    private Instant lastFetched = Instant.EPOCH;

    public CrlClient(String baseUrl, String apiKey, String userAgent) {
        this(baseUrl, apiKey, userAgent, HttpClient.newHttpClient());
    }

    public CrlClient(String baseUrl, String apiKey, String userAgent, HttpClient http) {
        this.baseUrl = baseUrl;
        this.apiKey = apiKey;
        this.userAgent = userAgent;
        this.http = http;
    }

    public void refresh() throws IOException, InterruptedException {
        HttpRequest.Builder req = HttpRequest.newBuilder()
                .uri(URI.create(baseUrl + "/revocation-list"))
                .header("Accept", "application/json")
                .GET();
        if (apiKey != null && !apiKey.isEmpty()) req.header("X-Forge-API-Key", apiKey);
        if (userAgent != null && !userAgent.isEmpty()) req.header("User-Agent", userAgent);
        lock.readLock().lock();
        try {
            if (!etag.isEmpty()) req.header("If-None-Match", etag);
        } finally {
            lock.readLock().unlock();
        }

        HttpResponse<byte[]> resp = http.send(req.build(), HttpResponse.BodyHandlers.ofByteArray());
        int code = resp.statusCode();
        if (code == 304) {
            touchLastFetched();
            return;
        }
        if (code == 401) throw new IOException("crl: invalid api key (401)");
        if (code == 429) throw new IOException("crl: rate limited (429)");
        if (code >= 500) throw new IOException("crl: server error " + code);
        if (code != 200) throw new IOException("crl: unexpected status " + code);

        Body body = MAPPER.readValue(resp.body(), Body.class);
        Set<String> next = new HashSet<>(body.licenseIds == null ? java.util.List.of() : body.licenseIds);
        String newEtag = resp.headers().firstValue("ETag").orElse("");
        lock.writeLock().lock();
        try {
            revoked = next;
            etag = newEtag;
            lastFetched = Instant.now();
        } finally {
            lock.writeLock().unlock();
        }
    }

    public boolean isRevoked(String licenseId) {
        lock.readLock().lock();
        try {
            return revoked.contains(licenseId);
        } finally {
            lock.readLock().unlock();
        }
    }

    public Instant lastFetched() {
        lock.readLock().lock();
        try {
            return lastFetched;
        } finally {
            lock.readLock().unlock();
        }
    }

    public int size() {
        lock.readLock().lock();
        try {
            return revoked.size();
        } finally {
            lock.readLock().unlock();
        }
    }

    private void touchLastFetched() {
        lock.writeLock().lock();
        try {
            lastFetched = Instant.now();
        } finally {
            lock.writeLock().unlock();
        }
    }

    static final class Body {
        public java.util.List<String> licenseIds;
        public String generatedAt;
    }
}
