// Soft fingerprint — SHA-256 over (MAC | hostname | CPU). Matches the canonical
// string format used by the Go / Python / Java SDKs so a license bound on one
// host can be verified by any-language verifier on the same host.

using System.Net.NetworkInformation;
using System.Net.Sockets;
using System.Security.Cryptography;
using System.Text;

namespace YourCo.Forge.Verifier;

public static class SoftFingerprint
{
    public static string Compute()
    {
        var mac = Safe(PrimaryMac());
        var hostname = Safe(Environment.MachineName);
        var cpu = Safe(CpuDescription());

        var canonical = $"{mac}|{hostname}|{cpu}".ToLowerInvariant();
        var hash = SHA256.HashData(Encoding.UTF8.GetBytes(canonical));
        return Convert.ToHexString(hash).ToLowerInvariant();
    }

    private static string PrimaryMac()
    {
        foreach (var ni in NetworkInterface.GetAllNetworkInterfaces())
        {
            if (ni.OperationalStatus != OperationalStatus.Up) continue;
            if (ni.NetworkInterfaceType == NetworkInterfaceType.Loopback) continue;
            var name = ni.Name.ToLowerInvariant();
            if (name.StartsWith("docker") || name.StartsWith("veth")
                || name.StartsWith("vmnet") || name.StartsWith("br-")
                || name.StartsWith("utun")) continue;
            // Skip tunneling / virtual-ish types
            if (ni.NetworkInterfaceType is NetworkInterfaceType.Tunnel
                or NetworkInterfaceType.Unknown) continue;

            var bytes = ni.GetPhysicalAddress().GetAddressBytes();
            if (bytes.Length == 0) continue;
            return string.Join(":", bytes.Select(b => b.ToString("x2")));
        }
        return "";
    }

    private static string CpuDescription() =>
        $"{System.Runtime.InteropServices.RuntimeInformation.ProcessArchitecture}:" +
        $"{System.Runtime.InteropServices.RuntimeInformation.OSDescription}:" +
        $"{Environment.ProcessorCount}";

    private static string Safe(string? s) =>
        string.IsNullOrEmpty(s) ? "unknown" : s;
}
