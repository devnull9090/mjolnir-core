/**
 * Verification of an uploaded .mjolnir archive.
 *
 * This is the line that keeps the content tier open to everyone: a content
 * release must be inert data the engine parses, never anything the machine
 * executes. Reject-by-default — unknown file kinds fail the scan rather
 * than slip through.
 *
 * Runs synchronously inside the /complete request for now. The contract
 * (findings recorded to release_scans, chunks to release_chunks) is what a
 * future Queue-consumer scanner would keep.
 */
import { unzipSync } from "fflate";

import type { Manifest } from "./manifest";
import { ManifestSchema } from "./manifest";
import { chunkIdToHex, parseTocChunkIds } from "./iostore";

/** Hard cap on the archive as stored; the Worker holds it in memory. */
export const MAX_ARCHIVE_BYTES = 50 * 1024 * 1024;
/** Zip-bomb guard: decompressed total may not exceed this. */
const MAX_UNPACKED_BYTES = 256 * 1024 * 1024;

export const SCANNER_VERSION = "ts-1";

/** File kinds a content archive may carry, by extension. */
const ALLOWED = new Set(["utoc", "ucas", "json", "md", "txt", "png", "jpg", "jpeg", "webp"]);

export interface Finding {
  level: "error" | "warning";
  code: string;
  message: string;
}

export interface ScanResult {
  verdict: "pass" | "fail";
  findings: Finding[];
  manifest: Manifest | null;
  /** Deduped raw 12-byte chunk IDs across every container in the archive. */
  chunkIds: Uint8Array[];
  containerCount: number;
  /** The unzipped archive, so later steps (signature verification) never
   *  unzip a second time. Empty when the zip did not open. */
  files: Record<string, Uint8Array>;
}

export function scanArchive(bytes: Uint8Array): ScanResult {
  const findings: Finding[] = [];
  const err = (code: string, message: string) => findings.push({ level: "error", code, message });
  const warn = (code: string, message: string) =>
    findings.push({ level: "warning", code, message });

  let files: Record<string, Uint8Array>;
  try {
    let unpacked = 0;
    files = unzipSync(bytes, {
      filter: (f) => {
        unpacked += f.originalSize ?? 0;
        if (unpacked > MAX_UNPACKED_BYTES) throw new Error("unpacked size limit exceeded");
        return true;
      },
    });
  } catch (e) {
    err("bad_zip", `Archive did not unzip: ${e instanceof Error ? e.message : e}`);
    return { verdict: "fail", findings, manifest: null, chunkIds: [], containerCount: 0, files: {} };
  }

  // Path hygiene before anything is trusted.
  for (const name of Object.keys(files)) {
    if (name.includes("..") || name.startsWith("/") || /^[a-zA-Z]:/.test(name)) {
      err("path_traversal", `Illegal path in archive: ${name}`);
    }
  }

  // Manifest.
  let manifest: Manifest | null = null;
  const rawManifest = files["mjolnir.json"];
  if (!rawManifest) {
    err("no_manifest", "mjolnir.json missing at the archive root.");
  } else {
    try {
      const parsed = ManifestSchema.safeParse(JSON.parse(new TextDecoder().decode(rawManifest)));
      if (parsed.success) {
        manifest = parsed.data;
      } else {
        err("bad_manifest", `mjolnir.json invalid: ${parsed.error.issues[0]?.message}`);
      }
    } catch {
      err("bad_manifest", "mjolnir.json is not valid JSON.");
    }
  }

  // File inventory: reject-by-default.
  const utocs: string[] = [];
  for (const [name, data] of Object.entries(files)) {
    if (name.endsWith("/") || data.length === 0) continue; // directory entries
    const ext = name.split(".").pop()?.toLowerCase() ?? "";
    if (!ALLOWED.has(ext)) {
      err("forbidden_file", `Content releases may not carry .${ext} files: ${name}`);
      continue;
    }
    if (ext === "utoc") {
      if (!name.startsWith("content/")) {
        warn("stray_container", `${name} is outside content/; the launcher will ignore it.`);
      }
      utocs.push(name);
    }
  }

  // Containers → chunk identity.
  const seen = new Map<string, Uint8Array>();
  for (const name of utocs) {
    try {
      const toc = parseTocChunkIds(files[name]);
      if (toc.encrypted) {
        err("encrypted_container", `${name} is encrypted; override containers must not be.`);
        continue;
      }
      const cas = name.slice(0, -"utoc".length) + "ucas";
      if (!files[cas]) err("orphan_utoc", `${name} has no matching .ucas.`);
      if (toc.chunkIds.length === 0) warn("empty_container", `${name} holds no chunks.`);
      for (const id of toc.chunkIds) seen.set(chunkIdToHex(id), id);
    } catch (e) {
      err("bad_container", `${name}: ${e instanceof Error ? e.message : e}`);
    }
  }
  for (const [name] of Object.entries(files)) {
    if (name.endsWith(".ucas") && !files[name.slice(0, -"ucas".length) + "utoc"]) {
      err("orphan_ucas", `${name} has no matching .utoc.`);
    }
  }

  if (utocs.length === 0 && findings.every((f) => f.level !== "error")) {
    err("no_content", "A content release must carry at least one container under content/.");
  }

  return {
    verdict: findings.some((f) => f.level === "error") ? "fail" : "pass",
    findings,
    manifest,
    chunkIds: [...seen.values()],
    containerCount: utocs.length,
    files,
  };
}
