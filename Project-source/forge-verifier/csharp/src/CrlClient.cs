// CRL client — GET /api/v1/revocation-list with ETag/If-None-Match caching.
// Thread-safe via a ReaderWriterLockSlim; reuse a single instance.

using System.Text.Json;
using System.Text.Json.Serialization;

namespace YourCo.Forge.Verifier;

public sealed class CrlClient
{
    private static readonly JsonSerializerOptions JsonOpts = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
    };

    private readonly string _baseUrl;
    private readonly string _apiKey;
    private readonly string _userAgent;
    private readonly HttpClient _http;

    private readonly ReaderWriterLockSlim _lock = new();
    private HashSet<string> _revoked = new();
    private string _etag = "";
    private DateTimeOffset _lastFetched;

    public CrlClient(string baseUrl, string apiKey, string userAgent, HttpClient? http = null)
    {
        _baseUrl = baseUrl;
        _apiKey = apiKey;
        _userAgent = userAgent;
        _http = http ?? new HttpClient();
    }

    public async Task RefreshAsync(CancellationToken ct = default)
    {
        using var req = new HttpRequestMessage(HttpMethod.Get, $"{_baseUrl}/revocation-list");
        req.Headers.TryAddWithoutValidation("Accept", "application/json");
        if (!string.IsNullOrEmpty(_apiKey)) req.Headers.TryAddWithoutValidation("X-Forge-API-Key", _apiKey);
        if (!string.IsNullOrEmpty(_userAgent)) req.Headers.TryAddWithoutValidation("User-Agent", _userAgent);
        _lock.EnterReadLock();
        try { if (!string.IsNullOrEmpty(_etag)) req.Headers.TryAddWithoutValidation("If-None-Match", _etag); }
        finally { _lock.ExitReadLock(); }

        using var resp = await _http.SendAsync(req, ct).ConfigureAwait(false);
        var code = (int)resp.StatusCode;
        if (code == 304)
        {
            TouchLastFetched();
            return;
        }
        if (code == 401) throw new InvalidOperationException("crl: invalid api key (401)");
        if (code == 429) throw new InvalidOperationException("crl: rate limited (429)");
        if (code >= 500) throw new InvalidOperationException($"crl: server error {code}");
        if (code != 200) throw new InvalidOperationException($"crl: unexpected status {code}");

        var stream = await resp.Content.ReadAsStreamAsync(ct).ConfigureAwait(false);
        var body = (await JsonSerializer.DeserializeAsync<CrlBody>(stream, JsonOpts, ct)
            .ConfigureAwait(false))!;
        var next = new HashSet<string>(body.LicenseIds ?? new List<string>());
        var newEtag = resp.Headers.ETag?.Tag ?? "";

        _lock.EnterWriteLock();
        try
        {
            _revoked = next;
            _etag = newEtag;
            _lastFetched = DateTimeOffset.UtcNow;
        }
        finally { _lock.ExitWriteLock(); }
    }

    public bool IsRevoked(string licenseId)
    {
        _lock.EnterReadLock();
        try { return _revoked.Contains(licenseId); }
        finally { _lock.ExitReadLock(); }
    }

    public DateTimeOffset LastFetched
    {
        get
        {
            _lock.EnterReadLock();
            try { return _lastFetched; }
            finally { _lock.ExitReadLock(); }
        }
    }

    public int Size
    {
        get
        {
            _lock.EnterReadLock();
            try { return _revoked.Count; }
            finally { _lock.ExitReadLock(); }
        }
    }

    private void TouchLastFetched()
    {
        _lock.EnterWriteLock();
        try { _lastFetched = DateTimeOffset.UtcNow; }
        finally { _lock.ExitWriteLock(); }
    }

    private sealed class CrlBody
    {
        [JsonPropertyName("license_ids")] public List<string>? LicenseIds { get; set; }
        [JsonPropertyName("generated_at")] public string? GeneratedAt { get; set; }
    }
}
