package com.yourco.forge.verifier;

import java.net.NetworkInterface;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Enumeration;
import java.util.HexFormat;
import java.util.Locale;

/**
 * Soft fingerprint — best-effort host identifier used when a license is
 * {@code binding=fingerprint-soft}. Hashes (MAC | hostname | CPU description).
 *
 * <p>Output is a lowercase SHA-256 hex string. The same canonical string format
 * is used across all Forge SDKs (Go / Python / Java / C# / Rust) so a single
 * license can be bound on one host and re-verified by any verifier.
 */
public final class SoftFingerprint {

    private SoftFingerprint() {}

    public static String compute() {
        String mac = safe(primaryMac());
        String hostname = safe(System.getenv().getOrDefault("HOSTNAME",
                System.getenv().getOrDefault("COMPUTERNAME", "")));
        if (hostname.isEmpty()) {
            try {
                hostname = safe(java.net.InetAddress.getLocalHost().getHostName());
            } catch (Exception ignored) {
                hostname = "unknown";
            }
        }
        String cpu = safe(cpuDescription());
        String canonical = (mac + "|" + hostname + "|" + cpu).toLowerCase(Locale.ROOT);
        try {
            MessageDigest md = MessageDigest.getInstance("SHA-256");
            return HexFormat.of().formatHex(md.digest(canonical.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 unavailable on this JVM", e);
        }
    }

    private static String primaryMac() {
        try {
            Enumeration<NetworkInterface> ifaces = NetworkInterface.getNetworkInterfaces();
            while (ifaces.hasMoreElements()) {
                NetworkInterface ni = ifaces.nextElement();
                if (ni.isLoopback() || !ni.isUp() || ni.isVirtual()) continue;
                String name = ni.getName().toLowerCase(Locale.ROOT);
                if (name.startsWith("docker") || name.startsWith("veth")
                        || name.startsWith("vmnet") || name.startsWith("br-")
                        || name.startsWith("utun")) continue;
                byte[] mac = ni.getHardwareAddress();
                if (mac == null || mac.length == 0) continue;
                StringBuilder sb = new StringBuilder(mac.length * 3);
                for (int i = 0; i < mac.length; i++) {
                    if (i > 0) sb.append(':');
                    sb.append(String.format("%02x", mac[i]));
                }
                return sb.toString();
            }
        } catch (Exception ignored) {
            // fall through
        }
        return "";
    }

    private static String cpuDescription() {
        return System.getProperty("os.arch", "") + ":"
                + System.getProperty("os.name", "") + ":"
                + Runtime.getRuntime().availableProcessors();
    }

    private static String safe(String s) {
        return (s == null || s.isEmpty()) ? "unknown" : s;
    }
}
