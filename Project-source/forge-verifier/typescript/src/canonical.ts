// Canonical JSON — RFC 8785 subset matching the Python reference SDK:
//   - object keys sorted lexicographically
//   - no insignificant whitespace
//   - numbers via JSON.stringify (V8 already emits shortest unique form)
//   - strings via JSON.stringify (handles escapes per RFC 8259)
//
// Used for HMAC-SHA256 body signing on heartbeat so request bytes match the
// server's recomputed canonical form regardless of which language emitted them.

export function canonicalize(value: unknown): string {
  if (value === null || typeof value !== "object") {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return "[" + value.map(canonicalize).join(",") + "]";
  }
  const entries = Object.entries(value as Record<string, unknown>)
    .filter(([, v]) => v !== undefined)
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
  return (
    "{" +
    entries
      .map(([k, v]) => JSON.stringify(k) + ":" + canonicalize(v))
      .join(",") +
    "}"
  );
}
