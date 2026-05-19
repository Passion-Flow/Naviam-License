// SM2 (GM/T 0003.2-2012) verification via Bouncy Castle .NET.
//
// Wire format matches the Python reference SDK:
//   - public_key    = ASCII hex, 128 chars (uncompressed X || Y)
//   - signature.bin = ASCII hex of GM/T raw r || s
//
// GM/T 0003 default user-id "1234567812345678" (also the Python default).

using System.Text;
using Org.BouncyCastle.Asn1;
using Org.BouncyCastle.Asn1.GM;
using Org.BouncyCastle.Crypto.Parameters;
using Org.BouncyCastle.Crypto.Signers;
using Org.BouncyCastle.Math;
using Org.BouncyCastle.Utilities.Encoders;

namespace YourCo.Forge.Verifier;

internal static class Sm2Verifier
{
    private static readonly byte[] DefaultUserId = Encoding.UTF8.GetBytes("1234567812345678");

    public static bool Verify(byte[] payload, byte[] publicKeyAsciiHex, byte[] signatureAsciiHex)
    {
        if (publicKeyAsciiHex.Length != 128) return false;

        byte[] xy;
        try { xy = Hex.Decode(publicKeyAsciiHex); }
        catch { return false; }
        if (xy.Length != 64) return false;

        var curve = GMNamedCurves.GetByName("sm2p256v1");
        var domain = new ECDomainParameters(curve.Curve, curve.G, curve.N, curve.H);
        var x = new BigInteger(1, xy[..32]);
        var y = new BigInteger(1, xy[32..64]);
        var pub = new ECPublicKeyParameters(curve.Curve.CreatePoint(x, y), domain);

        byte[] sig;
        try { sig = Hex.Decode(signatureAsciiHex); }
        catch { return false; }
        if (sig.Length < 32 || sig.Length % 2 != 0) return false;
        int half = sig.Length / 2;
        var r = new BigInteger(1, sig[..half]);
        var s = new BigInteger(1, sig[half..]);
        byte[] asn1 = EncodeAsn1(r, s);

        var signer = new SM2Signer();
        signer.Init(forSigning: false, new ParametersWithID(pub, DefaultUserId));
        signer.BlockUpdate(payload, 0, payload.Length);
        return signer.VerifySignature(asn1);
    }

    private static byte[] EncodeAsn1(BigInteger r, BigInteger s)
    {
        var seq = new DerSequence(new DerInteger(r), new DerInteger(s));
        return seq.GetDerEncoded();
    }
}
