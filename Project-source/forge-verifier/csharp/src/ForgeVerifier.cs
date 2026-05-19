// Forge License Authority Verifier — minimum viable .NET SDK.
// Ed25519 + parse + signature + expiry. RSA-PSS / SM2 / heartbeat / binding — README TODO.

using System;
using System.Collections.Generic;
using System.Formats.Tar;
using System.IO;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Serialization;
using Org.BouncyCastle.Crypto.Parameters;
using Org.BouncyCastle.Crypto.Signers;

namespace YourCo.Forge.Verifier;

public static class ForgeVerifier
{
    public const string ForgeMagic = "forg";
    public const string ForgeVersion = "1.0";

    private static readonly JsonSerializerOptions JsonOpts = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
    };

    public static Result Verify(string path, byte[] publicKey, DateTimeOffset now)
    {
        var f = Parse(path);
        return f.Verify(publicKey, now);
    }

    public static ForgeFile Parse(string path)
    {
        byte[]? payloadRaw = null;
        byte[]? signature = null;
        Metadata? metadata = null;

        using var stream = File.OpenRead(path);
        using var tar = new TarReader(stream);
        while (tar.GetNextEntry() is { } entry)
        {
            using var ms = new MemoryStream();
            entry.DataStream?.CopyTo(ms);
            var buf = ms.ToArray();
            switch (entry.Name)
            {
                case "payload.json":
                    payloadRaw = buf;
                    break;
                case "signature.bin":
                    signature = buf;
                    break;
                case "metadata.json":
                    metadata = JsonSerializer.Deserialize<Metadata>(buf, JsonOpts);
                    break;
            }
        }

        if (payloadRaw is null || signature is null || metadata is null)
            throw new ForgeException("forge file missing required entry", Status.Malformed);
        if (metadata.Magic != ForgeMagic)
            throw new ForgeException($"bad magic: {metadata.Magic}", Status.Malformed);

        var payload = JsonSerializer.Deserialize<Payload>(payloadRaw, JsonOpts)
                      ?? throw new ForgeException("payload.json malformed", Status.Malformed);

        return new ForgeFile(payload, payloadRaw, signature, metadata);
    }

    public sealed class ForgeFile
    {
        public Payload Payload { get; }
        public byte[] PayloadRaw { get; }
        public byte[] Signature { get; }
        public Metadata Metadata { get; }

        internal ForgeFile(Payload p, byte[] raw, byte[] sig, Metadata m)
        {
            Payload = p; PayloadRaw = raw; Signature = sig; Metadata = m;
        }

        public Result Verify(byte[] publicKey, DateTimeOffset now)
        {
            var result = new Result
            {
                Status = Status.Valid,
                LicenseId = Payload.LicenseId,
                ExpiresAt = Payload.ExpiresAt,
                Binding = Payload.Binding,
                FingerprintMustMatch = Payload.BoundFingerprint,
            };

            switch (Metadata.Algorithm)
            {
                case "ed25519":
                    VerifyEd25519(publicKey);
                    break;
                case "rsa2048":
                case "rsa4096":
                    VerifyRsaPss(publicKey, Metadata.Algorithm);
                    break;
                case "sm2":
                    if (!Sm2Verifier.Verify(PayloadRaw, publicKey, Signature))
                        throw new ForgeException("signature invalid", Status.SignatureInvalid);
                    break;
                default:
                    throw new ForgeException(
                        $"algorithm unsupported: {Metadata.Algorithm}",
                        Status.AlgorithmUnsupported);
            }

            if (now >= Payload.ExpiresAt)
            {
                result.Status = Status.Expired;
                throw new ForgeException("license expired", result);
            }
            return result;
        }

        private void VerifyRsaPss(byte[] derPublicKey, string algorithm)
        {
            int expectedBits = algorithm == "rsa4096" ? 4096 : 2048;
            using var rsa = RSA.Create();
            rsa.ImportSubjectPublicKeyInfo(derPublicKey, out _);
            int bits = rsa.KeySize;
            if (bits != expectedBits)
                throw new ForgeException(
                    $"rsa modulus is {bits} bits, expected {expectedBits}",
                    Status.SignatureInvalid);
            bool ok = rsa.VerifyData(
                PayloadRaw, Signature,
                HashAlgorithmName.SHA256, RSASignaturePadding.Pss);
            if (!ok)
                throw new ForgeException("signature invalid", Status.SignatureInvalid);
        }

        private void VerifyEd25519(byte[] rawPublicKey)
        {
            if (rawPublicKey.Length != 32)
                throw new ForgeException(
                    $"ed25519 public key must be 32 bytes; got {rawPublicKey.Length}",
                    Status.SignatureInvalid);

            var pub = new Ed25519PublicKeyParameters(rawPublicKey, 0);
            var verifier = new Ed25519Signer();
            verifier.Init(forSigning: false, pub);
            verifier.BlockUpdate(PayloadRaw, 0, PayloadRaw.Length);
            if (!verifier.VerifySignature(Signature))
                throw new ForgeException("signature invalid", Status.SignatureInvalid);
        }
    }

    public enum Status { Valid, Expired, Revoked, SignatureInvalid, AlgorithmUnsupported, Malformed }

    public sealed class Metadata
    {
        [JsonPropertyName("magic")] public string Magic { get; set; } = "";
        [JsonPropertyName("forge_version")] public string ForgeVersion { get; set; } = "";
        [JsonPropertyName("algorithm")] public string Algorithm { get; set; } = "";
        [JsonPropertyName("key_id")] public string KeyId { get; set; } = "";
        [JsonPropertyName("signed_at")] public DateTimeOffset SignedAt { get; set; }
    }

    public sealed class Payload
    {
        [JsonPropertyName("protocol_version")] public string ProtocolVersion { get; set; } = "";
        [JsonPropertyName("license_id")] public string LicenseId { get; set; } = "";
        [JsonPropertyName("customer_id")] public string CustomerId { get; set; } = "";
        [JsonPropertyName("product_id")] public string ProductId { get; set; } = "";
        [JsonPropertyName("mode")] public string Mode { get; set; } = "";
        [JsonPropertyName("scope")] public string Scope { get; set; } = "";
        [JsonPropertyName("binding")] public string Binding { get; set; } = "";
        [JsonPropertyName("bound_fingerprint")] public string? BoundFingerprint { get; set; }
        [JsonPropertyName("issued_at")] public DateTimeOffset IssuedAt { get; set; }
        [JsonPropertyName("expires_at")] public DateTimeOffset ExpiresAt { get; set; }
        [JsonPropertyName("features")] public Dictionary<string, object>? Features { get; set; }
        [JsonPropertyName("limits")] public Dictionary<string, object>? Limits { get; set; }
    }

    public sealed class Result
    {
        public Status Status { get; set; }
        public string LicenseId { get; set; } = "";
        public DateTimeOffset ExpiresAt { get; set; }
        public string Binding { get; set; } = "";
        public string? FingerprintMustMatch { get; set; }
    }

    public sealed class ForgeException : Exception
    {
        public Status Status { get; }
        public Result? Result { get; }

        public ForgeException(string msg, Status status) : base(msg) { Status = status; }
        public ForgeException(string msg, Result result) : base(msg)
        {
            Status = result.Status;
            Result = result;
        }
    }
}
