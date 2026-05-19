using System;
using System.IO;
using System.Text.Json;
using Xunit;
using YourCo.Forge.Verifier;

namespace YourCo.Forge.Verifier.Tests;

public class ForgeVerifierTests
{
    // Same vectors Python / Go / Java consume.
    private static readonly string VectorRoot =
        Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", "..", "spec", "test-vectors"));

    private static byte[] LoadPublicKey(string vector)
    {
        var path = Path.Combine(VectorRoot, vector, "keypair.json");
        var doc = JsonDocument.Parse(File.ReadAllBytes(path));
        return Convert.FromBase64String(doc.RootElement.GetProperty("public_key_b64").GetString()!);
    }

    private static string ForgeFile(string vector)
        => Path.Combine(VectorRoot, vector, "expected.forge");

    [Fact]
    public void Vector001_OfflineNone()
    {
        var pk = LoadPublicKey("001-ed25519-offline-none");
        var r = ForgeVerifier.Verify(
            ForgeFile("001-ed25519-offline-none"),
            pk,
            DateTimeOffset.Parse("2026-06-01T00:00:00Z"));
        Assert.Equal(ForgeVerifier.Status.Valid, r.Status);
        Assert.Equal("vector-001-ed25519-offline-none", r.LicenseId);
        Assert.Equal("none", r.Binding);
    }

    [Fact]
    public void Expired()
    {
        var pk = LoadPublicKey("001-ed25519-offline-none");
        var ex = Assert.Throws<ForgeVerifier.ForgeException>(() =>
            ForgeVerifier.Verify(
                ForgeFile("001-ed25519-offline-none"),
                pk,
                DateTimeOffset.Parse("2099-01-01T00:00:00Z")));
        Assert.Equal(ForgeVerifier.Status.Expired, ex.Status);
    }

    [Fact]
    public void Vector004_Sm2_OfflineNone()
    {
        var pk = LoadPublicKey("004-sm2-offline-none");
        var r = ForgeVerifier.Verify(
            ForgeFile("004-sm2-offline-none"),
            pk,
            DateTimeOffset.Parse("2026-06-01T00:00:00Z"));
        Assert.Equal(ForgeVerifier.Status.Valid, r.Status);
        Assert.Equal("vector-004-sm2-offline-none", r.LicenseId);
    }

    [Fact]
    public void TamperedSignature()
    {
        var pk = LoadPublicKey("001-ed25519-offline-none");
        var f = ForgeVerifier.Parse(ForgeFile("001-ed25519-offline-none"));
        f.Signature[0] ^= 0x01;
        var ex = Assert.Throws<ForgeVerifier.ForgeException>(() =>
            f.Verify(pk, DateTimeOffset.Parse("2026-06-01T00:00:00Z")));
        Assert.Equal(ForgeVerifier.Status.SignatureInvalid, ex.Status);
    }
}
