package com.yourco.forge.verifier;

import org.bouncycastle.asn1.gm.GMNamedCurves;
import org.bouncycastle.asn1.x9.X9ECParameters;
import org.bouncycastle.crypto.params.ECDomainParameters;
import org.bouncycastle.crypto.params.ECPublicKeyParameters;
import org.bouncycastle.crypto.params.ParametersWithID;
import org.bouncycastle.crypto.signers.SM2Signer;
import org.bouncycastle.util.encoders.Hex;

import java.math.BigInteger;
import java.nio.charset.StandardCharsets;

/**
 * SM2 (GM/T 0003.2-2012) verification via Bouncy Castle.
 *
 * <p>Wire format matches the Python reference SDK:
 * <ul>
 *   <li>{@code public_key} — ASCII hex, 128 chars (uncompressed X ‖ Y)</li>
 *   <li>{@code signature.bin} — ASCII hex of GM/T raw {@code r ‖ s}</li>
 * </ul>
 *
 * <p>GM/T 0003 default user-id {@code "1234567812345678"} is used (also the Python default).
 */
final class Sm2Verifier {

    private static final String SM2P256V1 = "sm2p256v1";
    private static final byte[] DEFAULT_USER_ID = "1234567812345678".getBytes(StandardCharsets.UTF_8);

    static boolean verify(byte[] payload, byte[] publicKeyAsciiHex, byte[] signatureAsciiHex) {
        if (publicKeyAsciiHex.length != 128) {
            return false;
        }
        byte[] xy;
        try {
            xy = Hex.decode(publicKeyAsciiHex);
        } catch (Exception e) {
            return false;
        }
        if (xy.length != 64) return false;

        X9ECParameters params = GMNamedCurves.getByName(SM2P256V1);
        ECDomainParameters domain = new ECDomainParameters(
                params.getCurve(), params.getG(), params.getN(), params.getH());
        BigInteger x = new BigInteger(1, java.util.Arrays.copyOfRange(xy, 0, 32));
        BigInteger y = new BigInteger(1, java.util.Arrays.copyOfRange(xy, 32, 64));
        ECPublicKeyParameters pub = new ECPublicKeyParameters(
                params.getCurve().createPoint(x, y), domain);

        byte[] sig;
        try {
            sig = Hex.decode(signatureAsciiHex);
        } catch (Exception e) {
            return false;
        }
        if (sig.length < 32 || sig.length % 2 != 0) return false;
        int half = sig.length / 2;
        BigInteger r = new BigInteger(1, java.util.Arrays.copyOfRange(sig, 0, half));
        BigInteger s = new BigInteger(1, java.util.Arrays.copyOfRange(sig, half, sig.length));
        byte[] asn1 = encodeAsn1(r, s);

        SM2Signer signer = new SM2Signer();
        signer.init(false, new ParametersWithID(pub, DEFAULT_USER_ID));
        signer.update(payload, 0, payload.length);
        return signer.verifySignature(asn1);
    }

    /** BC's SM2Signer accepts ASN.1 DER (SEQUENCE { INTEGER r, INTEGER s }). */
    private static byte[] encodeAsn1(BigInteger r, BigInteger s) {
        byte[] rb = trimLead(r.toByteArray());
        byte[] sb = trimLead(s.toByteArray());
        // INTEGERs must be unsigned: if high bit set, prepend 0x00
        byte[] rEnc = needsPad(rb) ? prependZero(rb) : rb;
        byte[] sEnc = needsPad(sb) ? prependZero(sb) : sb;
        int inner = 2 + rEnc.length + 2 + sEnc.length;
        byte[] out = new byte[2 + inner];
        int i = 0;
        out[i++] = 0x30;
        out[i++] = (byte) inner;
        out[i++] = 0x02;
        out[i++] = (byte) rEnc.length;
        System.arraycopy(rEnc, 0, out, i, rEnc.length); i += rEnc.length;
        out[i++] = 0x02;
        out[i++] = (byte) sEnc.length;
        System.arraycopy(sEnc, 0, out, i, sEnc.length);
        return out;
    }

    private static byte[] trimLead(byte[] b) {
        int i = 0;
        while (i < b.length - 1 && b[i] == 0) i++;
        if (i == 0) return b;
        byte[] o = new byte[b.length - i];
        System.arraycopy(b, i, o, 0, o.length);
        return o;
    }

    private static boolean needsPad(byte[] b) {
        return b.length > 0 && (b[0] & 0x80) != 0;
    }

    private static byte[] prependZero(byte[] b) {
        byte[] o = new byte[b.length + 1];
        System.arraycopy(b, 0, o, 1, b.length);
        return o;
    }

    private Sm2Verifier() {}
}
