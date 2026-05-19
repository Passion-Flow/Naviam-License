// Heartbeat client — POSTs to /api/v1/licenses/{id}/heartbeat with HMAC-SHA256
// body signature. Wire protocol matches Go / Python SDKs byte-for-byte.

using System.Net;
using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace YourCo.Forge.Verifier;

public sealed class HeartbeatClient
{
    private static readonly JsonSerializerOptions JsonOpts = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
    };

    private readonly string _baseUrl;
    private readonly string _apiKey;
    private readonly string _userAgent;
    private readonly HttpClient _http;

    public HeartbeatClient(string baseUrl, string apiKey, string userAgent, HttpClient? http = null)
    {
        _baseUrl = baseUrl;
        _apiKey = apiKey;
        _userAgent = userAgent;
        _http = http ?? new HttpClient();
    }

    public async Task<HeartbeatResponse> SendAsync(string licenseId, string fingerprint, CancellationToken ct = default)
    {
        var body = new HeartbeatRequest
        {
            LicenseId = licenseId,
            Fingerprint = fingerprint,
            VerifierVersion = _userAgent,
            Nonce = RandomNonceHex(),
            ReportedAt = DateTimeOffset.UtcNow.ToString("o"),
        };
        var raw = JsonSerializer.SerializeToUtf8Bytes(body, JsonOpts);
        var sig = HmacHex(_apiKey, raw);

        using var req = new HttpRequestMessage(HttpMethod.Post,
            $"{_baseUrl}/licenses/{licenseId}/heartbeat")
        {
            Content = new ByteArrayContent(raw)
            {
                Headers = { { "Content-Type", "application/json" } },
            },
        };
        req.Headers.TryAddWithoutValidation("X-Forge-API-Key", _apiKey);
        req.Headers.TryAddWithoutValidation("X-Forge-Signature", $"sha256={sig}");
        if (!string.IsNullOrEmpty(_userAgent))
        {
            req.Headers.TryAddWithoutValidation("User-Agent", _userAgent);
        }

        using var resp = await _http.SendAsync(req, ct).ConfigureAwait(false);
        switch ((int)resp.StatusCode)
        {
            case 401: throw new InvalidOperationException("heartbeat: invalid api key (401)");
            case 429: throw new InvalidOperationException("heartbeat: rate limited (429)");
            case >= 500: throw new InvalidOperationException($"heartbeat: server error {(int)resp.StatusCode}");
        }
        var stream = await resp.Content.ReadAsStreamAsync(ct).ConfigureAwait(false);
        return (await JsonSerializer.DeserializeAsync<HeartbeatResponse>(
            stream, JsonOpts, ct).ConfigureAwait(false))!;
    }

    internal static string HmacHex(string key, byte[] body)
    {
        using var mac = new HMACSHA256(Encoding.UTF8.GetBytes(key));
        return Convert.ToHexString(mac.ComputeHash(body)).ToLowerInvariant();
    }

    private static string RandomNonceHex()
    {
        Span<byte> b = stackalloc byte[16];
        RandomNumberGenerator.Fill(b);
        return Convert.ToHexString(b).ToLowerInvariant();
    }
}

public sealed class HeartbeatRequest
{
    [JsonPropertyName("license_id")] public string LicenseId { get; set; } = "";
    [JsonPropertyName("fingerprint")] public string Fingerprint { get; set; } = "";
    [JsonPropertyName("verifier_version")] public string VerifierVersion { get; set; } = "";
    [JsonPropertyName("nonce")] public string Nonce { get; set; } = "";
    [JsonPropertyName("reported_at")] public string ReportedAt { get; set; } = "";
}

public sealed class HeartbeatResponse
{
    [JsonPropertyName("ok")] public bool Ok { get; set; }
    [JsonPropertyName("license_status")] public string LicenseStatus { get; set; } = "";
    [JsonPropertyName("multi_env_anomaly")] public bool MultiEnvAnomaly { get; set; }
    [JsonPropertyName("next_heartbeat_after_seconds")] public int NextHeartbeatAfterSeconds { get; set; }
    [JsonPropertyName("reason")] public string? Reason { get; set; }
}
