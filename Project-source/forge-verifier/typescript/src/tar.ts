// Minimal ustar (POSIX 1003.1-1988) reader — no external deps.
//
// `.forge` files contain exactly three entries (payload.json / signature.bin /
// metadata.json). We don't need write support, extended-header (PAX) support,
// or directory traversal — just walk the 512-byte header → content blocks.

const BLOCK_SIZE = 512;

export interface TarEntry {
  name: string;
  size: number;
  content: Uint8Array;
}

export function readTar(bytes: Uint8Array): TarEntry[] {
  const entries: TarEntry[] = [];
  let offset = 0;
  while (offset + BLOCK_SIZE <= bytes.length) {
    const header = bytes.subarray(offset, offset + BLOCK_SIZE);
    if (header.every((b) => b === 0)) break;

    const name = readCString(header, 0, 100);
    const size = parseOctal(header, 124, 12);
    if (size < 0 || !Number.isFinite(size)) {
      throw new Error(`tar: malformed size for entry ${name}`);
    }
    const start = offset + BLOCK_SIZE;
    if (start + size > bytes.length) {
      throw new Error(`tar: entry ${name} declared ${size} bytes but archive truncated`);
    }
    if (name !== "") {
      entries.push({ name, size, content: bytes.subarray(start, start + size) });
    }
    const pad = size === 0 ? 0 : BLOCK_SIZE - (size % BLOCK_SIZE || BLOCK_SIZE);
    offset = start + size + pad;
  }
  return entries;
}

function readCString(buf: Uint8Array, offset: number, max: number): string {
  let end = offset;
  while (end < offset + max && buf[end] !== 0) end++;
  return new TextDecoder("utf-8").decode(buf.subarray(offset, end));
}

function parseOctal(buf: Uint8Array, offset: number, len: number): number {
  let s = "";
  for (let i = offset; i < offset + len; i++) {
    const c = buf[i];
    if (c === undefined || c === 0 || c === 0x20) break;
    s += String.fromCharCode(c);
  }
  if (s === "") return 0;
  return parseInt(s, 8);
}
