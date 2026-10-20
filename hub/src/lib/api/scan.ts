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
import { Unzip, UnzipInflate } from "fflate";

import type { DeclaredChanges } from "./changes";
import { DeclaredChangesSchema, MAX_CHANGES_BYTES } from "./changes";
import type { Manifest } from "./manifest";
import { ManifestSchema } from "./manifest";
import { chunkIdToHex, parseTocChunkIds } from "./iostore";
import { Sha256 } from "./sha256";

/** Hard cap on the archive as stored; the Worker holds it in memory. Under
 *  the 100 MB request body Cloudflare takes; a remastered map runs to 70 MB.
 *  Its members are hashed as they stream (scanArchive), never held whole. */
export const MAX_ARCHIVE_BYTES = 90 * 1024 * 1024;
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
  /** The declared change list, when the archive carries a valid one. */
  changes: DeclaredChanges | null;
  /** Deduped raw 12-byte chunk IDs across every container in the archive. */
  chunkIds: Uint8Array[];
  containerCount: number;
  /** The members the scan reads (`.json`, `.utoc`), unzipped, so later steps
   *  (signature verification) never unzip a second time. Empty when the zip
   *  did not open. */
  files: Record<string, Uint8Array>;
  /** Every member's SHA-256 (hex) and size, directory entries included. */
  hashes: Record<string, string>;
  sizes: Record<string, number>;
}

/** Members read whole; everything else (container data, images) is hashed
 *  as it streams out and dropped: held whole beside the archive, a
 *  remastered map's containers went past the Worker's 128 MB. */
const READ_WHOLE = /\.(json|utoc)$/i;

/** How much of the archive is handed to the unzip at a time (unpack). */
const PUSH_SLICE = 256 * 1024;

/** The archive's members, streamed: `files` the ones READ_WHOLE keeps, the
 *  hash and size of each. Throws on a broken zip or past MAX_UNPACKED_BYTES. */
function unpack(bytes: Uint8Array) {
  const files: Record<string, Uint8Array> = {};
  const hashes: Record<string, string> = {};
  const sizes: Record<string, number> = {};
  const open = new Set<string>();
  let unpacked = 0;
  let failure: unknown = null;
  const unzip = new Unzip((file) => {
    const keep = READ_WHOLE.test(file.name);
    const parts: Uint8Array[] = [];
    const hash = new Sha256();
    let size = 0;
    open.add(file.name);
    file.ondata = (e, chunk, final) => {
      if (failure) return;
      if (e) {
        failure = e;
        return;
      }
      size += chunk.length;
      unpacked += chunk.length;
      if (unpacked > MAX_UNPACKED_BYTES) {
        failure = new Error("unpacked size limit exceeded");
        file.terminate();
        return;
      }
      hash.update(chunk);
      if (keep) parts.push(chunk.slice());
      if (final) {
        open.delete(file.name);
        sizes[file.name] = size;
        hashes[file.name] = hash.hex();
        if (keep) {
          const whole = new Uint8Array(size);
          let at = 0;
          for (const part of parts) {
            whole.set(part, at);
            at += part.length;
          }
          files[file.name] = whole;
        }
      }
    };
    file.start();
  });
  unzip.register(UnzipInflate);
  // In slices: fflate inflates all the input it is handed in one go, so one
  // push of the whole archive inflated a member whole, and the CE runtime's
  // 92 MB container (37 MB packed) took the Worker past its memory
  // (Cloudflare 1102, runtime 1.12.0, 2026-10-20). A slice inflates to a
  // few MB at most, hashed and dropped.
  for (let at = 0; at < bytes.length; at += PUSH_SLICE) {
    unzip.push(bytes.subarray(at, at + PUSH_SLICE), at + PUSH_SLICE >= bytes.length);
    if (failure) break;
  }
  if (bytes.length === 0) unzip.push(bytes, true);
  if (failure) throw failure;
  if (open.size > 0) throw new Error(`truncated member ${[...open][0]}`);
  return { files, hashes, sizes };
}

export function scanArchive(bytes: Uint8Array): ScanResult {
  const findings: Finding[] = [];
  const err = (code: string, message: string) => findings.push({ level: "error", code, message });
  const warn = (code: string, message: string) =>
    findings.push({ level: "warning", code, message });

  let files: Record<string, Uint8Array>;
  let hashes: Record<string, string>;
  let sizes: Record<string, number>;
  try {
    ({ files, hashes, sizes } = unpack(bytes));
  } catch (e) {
    err("bad_zip", `Archive did not unzip: ${e instanceof Error ? e.message : e}`);
    return {
      verdict: "fail",
      findings,
      manifest: null,
      changes: null,
      chunkIds: [],
      containerCount: 0,
      files: {},
      hashes: {},
      sizes: {},
    };
  }

  // Path hygiene before anything is trusted.
  for (const name of Object.keys(sizes)) {
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
        if (!manifest.summary?.trim()) {
          warn(
            "no_summary",
            "The manifest has no summary, so cards and the mod page say nothing " +
              "about what this is. Set one in the project settings and re-export.",
          );
        }
      } else {
        err("bad_manifest", `mjolnir.json invalid: ${parsed.error.issues[0]?.message}`);
      }
    } catch {
      err("bad_manifest", "mjolnir.json is not valid JSON.");
    }
  }

  // The declared change list. Optional — older editors don't write one —
  // but present-and-broken is an error: it is machine-written, so a file
  // that fails the schema means tampering or a bug worth stopping.
  let changes: DeclaredChanges | null = null;
  const rawChanges = files["changes.json"];
  if (!rawChanges) {
    // A map pack adds a map; it edits nothing, so it has no change list.
    if (manifest?.type !== "map") warn(
      "no_changes",
      "No changes.json: the mod page cannot show players what this release edits. " +
        "Export from a current tag editor to include the declared change list.",
    );
  } else if (rawChanges.length > MAX_CHANGES_BYTES) {
    err("bad_changes", `changes.json is ${rawChanges.length} bytes; the cap is ${MAX_CHANGES_BYTES}.`);
  } else {
    try {
      const parsed = DeclaredChangesSchema.safeParse(
        JSON.parse(new TextDecoder().decode(rawChanges)),
      );
      if (parsed.success) {
        changes = parsed.data;
      } else {
        err("bad_changes", `changes.json invalid: ${parsed.error.issues[0]?.message}`);
      }
    } catch {
      err("bad_changes", "changes.json is not valid JSON.");
    }
  }

  // File inventory: reject-by-default.
  const utocs: string[] = [];
  for (const [name, size] of Object.entries(sizes)) {
    if (name.endsWith("/") || size === 0) continue; // directory entries
    const ext = name.split(".").pop()?.toLowerCase() ?? "";
    // A map's own data beside its level file: a remastered map's foliage
    // placements (foliage.bin, read by the level loader, never run).
    const mapData = ext === "bin" && name.startsWith("map/");
    if (!ALLOWED.has(ext) && !mapData) {
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
      if (!(cas in sizes)) err("orphan_utoc", `${name} has no matching .ucas.`);
      if (toc.chunkIds.length === 0) warn("empty_container", `${name} holds no chunks.`);
      for (const id of toc.chunkIds) seen.set(chunkIdToHex(id), id);
    } catch (e) {
      err("bad_container", `${name}: ${e instanceof Error ? e.message : e}`);
    }
  }
  for (const name of Object.keys(sizes)) {
    if (name.endsWith(".ucas") && !(name.slice(0, -"ucas".length) + "utoc" in sizes)) {
      err("orphan_ucas", `${name} has no matching .utoc.`);
    }
  }

  // A map pack: the loader's level file and the map's registration row,
  // and containers named for the map (docs/map_distribution.md).
  if (manifest?.type === "map" && manifest.map) {
    const code = manifest.map.code;
    for (const name of ["map/level.json", "map/registration.json"]) {
      const raw = files[name];
      if (!raw) {
        err("map_file_missing", `A map pack carries ${name}.`);
        continue;
      }
      try {
        JSON.parse(new TextDecoder().decode(raw));
      } catch {
        err("bad_map_file", `${name} is not valid JSON.`);
      }
    }
    for (const name of utocs) {
      if (!name.includes(`-${code}_P.`)) {
        warn(
          "foreign_container",
          `${name} is not named for ${code}; shared content belongs in the runtime pack ` +
            "(mjolnir-ce-runtime), not in a map.",
        );
      }
    }
  }

  if (utocs.length === 0 && findings.every((f) => f.level !== "error")) {
    err("no_content", "A content release must carry at least one container under content/.");
  }

  return {
    verdict: findings.some((f) => f.level === "error") ? "fail" : "pass",
    findings,
    manifest,
    changes,
    chunkIds: [...seen.values()],
    containerCount: utocs.length,
    files,
    hashes,
    sizes,
  };
}
