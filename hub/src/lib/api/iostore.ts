/**
 * Just enough IoStore TOC parsing to enumerate chunk IDs.
 *
 * Mirrors crates/ue-iostore/src/toc.rs (the authority on this format —
 * validated by round-tripping every shipped container byte-exactly). The
 * scanner only needs identity, not data: the header's fixed offsets plus the
 * 12-byte chunk-ID array that immediately follows it. Nothing here touches
 * compression, the directory index, or the perfect hash.
 */

const TOC_MAGIC = "-==--==--==--==-";

export interface TocSummary {
  version: number;
  containerId: bigint;
  /** Raw 12-byte chunk IDs, exactly as they sit in the file. */
  chunkIds: Uint8Array[];
  /** True when the encryption GUID is non-zero or the encrypted flag is set. */
  encrypted: boolean;
}

export function parseTocChunkIds(bytes: Uint8Array): TocSummary {
  if (bytes.length < 144) throw new Error("too short to be a .utoc");
  for (let i = 0; i < 16; i++) {
    if (bytes[i] !== TOC_MAGIC.charCodeAt(i)) throw new Error("bad .utoc magic");
  }
  const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);

  const version = bytes[16];
  const headerSize = dv.getUint32(20, true);
  const entryCount = dv.getUint32(24, true);
  const containerId = dv.getBigUint64(56, true);
  const flags = bytes[80];

  let encrypted = (flags & 0x02) !== 0;
  for (let i = 64; i < 80; i++) if (bytes[i] !== 0) encrypted = true;

  if (headerSize < 144 || headerSize > bytes.length) throw new Error("bad header size");
  const idsEnd = headerSize + entryCount * 12;
  if (idsEnd > bytes.length) throw new Error("chunk ID array runs past the file");
  // An override container is small by construction; a TOC claiming an
  // absurd entry count is malformed or hostile.
  if (entryCount > 1_000_000) throw new Error("unreasonable chunk count");

  const chunkIds: Uint8Array[] = [];
  for (let i = 0; i < entryCount; i++) {
    chunkIds.push(bytes.slice(headerSize + i * 12, headerSize + (i + 1) * 12));
  }
  return { version, containerId, chunkIds, encrypted };
}

export function chunkIdToHex(id: Uint8Array): string {
  return Array.from(id, (b) => b.toString(16).padStart(2, "0")).join("");
}
