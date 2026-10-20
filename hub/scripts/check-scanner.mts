// Runs the upload scanner and signature check over real .mjolnir archives,
// and holds its streamed hashes against fflate's whole-archive unzip and
// node's SHA-256: the scanner hashes members as they stream (they do not fit
// the Worker's memory whole), so this is what says the streaming is right.
//
//   npx tsx scripts/check-scanner.mts <archive.mjolnir>...
//
// Prints each archive's verdict, findings and signature state, and the peak
// heap the scan took; exits 1 on any hash disagreement.

import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { unzipSync, zipSync } from "fflate";

import { scanArchive, scanArchiveStream } from "../src/lib/api/scan";
import { checkArchiveSignature } from "../src/lib/api/signing";
import { Sha256 } from "../src/lib/api/sha256";

let failed = false;

// The hash itself, against node's, across block boundaries and split updates.
for (const n of [0, 1, 55, 56, 63, 64, 65, 119, 120, 1000, 70_000]) {
  const data = new Uint8Array(n).map((_, i) => (i * 31 + 7) & 255);
  const want = createHash("sha256").update(data).digest("hex");
  const whole = new Sha256().update(data).hex();
  const split = new Sha256().update(data.subarray(0, n >> 1)).update(data.subarray(n >> 1)).hex();
  if (whole !== want || split !== want) {
    console.error(`sha256 of ${n} bytes: ${whole} / ${split}, want ${want}`);
    failed = true;
  }
}

// A zip with a directory entry, an empty member, and stored and deflated
// members, built here (no fixture file). Zips other tools write (data
// descriptors from Python's zipfile on an unseekable stream, PowerShell's
// Compress-Archive) were checked by passing them on the command line,
// 2026-10-15.
const synthetic = zipSync({
  "mjolnir.json": [new TextEncoder().encode('{"schema_version":1,"name":"t","version":"1.0.0","type":"content"}'), { level: 6 }],
  "content/": new Uint8Array(0),
  "docs/empty.txt": new Uint8Array(0),
  "docs/stored.md": [new TextEncoder().encode("stored ".repeat(500)), { level: 0 }],
  "docs/deflated.md": [new TextEncoder().encode("deflated ".repeat(500)), { level: 9 }],
});

const inputs: [string, Uint8Array][] = [["(synthetic)", synthetic]];
for (const file of process.argv.slice(2)) inputs.push([file, new Uint8Array(await readFile(file))]);

for (const [file, bytes] of inputs) {
  const before = process.memoryUsage().heapUsed;
  const scan = scanArchive(bytes);
  const peak = process.memoryUsage().heapUsed - before;

  const whole = unzipSync(bytes);
  for (const [name, data] of Object.entries(whole)) {
    const want = createHash("sha256").update(data).digest("hex");
    if (scan.hashes[name] !== want || scan.sizes[name] !== data.length) {
      console.error(`${path.basename(file)}: ${name} hash/size disagrees`);
      failed = true;
    }
  }
  if (Object.keys(scan.hashes).length !== Object.keys(whole).length) {
    console.error(`${path.basename(file)}: member count disagrees`);
    failed = true;
  }

  // The scan /complete runs: the archive streamed in uneven pieces, as R2's
  // body arrives. It must find what the in-memory scan finds, and hash the
  // archive as node does.
  const piece = 1024 * 1024 + 7;
  const stream = new ReadableStream<Uint8Array>({
    start(ctl) {
      for (let at = 0; at < bytes.length; at += piece) ctl.enqueue(bytes.slice(at, at + piece));
      ctl.close();
    },
  });
  const streamed = await scanArchiveStream(stream, Number.MAX_SAFE_INTEGER);
  const same =
    JSON.stringify(streamed.scan.hashes) === JSON.stringify(scan.hashes) &&
    JSON.stringify(streamed.scan.sizes) === JSON.stringify(scan.sizes) &&
    streamed.scan.verdict === scan.verdict &&
    streamed.scan.findings.map((f) => f.code).join() === scan.findings.map((f) => f.code).join() &&
    streamed.scan.chunkIds.length === scan.chunkIds.length &&
    streamed.size === bytes.length &&
    streamed.sha256 === createHash("sha256").update(bytes).digest("hex");
  if (!same) {
    console.error(`${path.basename(file)}: the streamed scan disagrees with the in-memory one`);
    failed = true;
  }
  const capped = await scanArchiveStream(
    new ReadableStream<Uint8Array>({ start: (ctl) => (ctl.enqueue(bytes), ctl.close()) }),
    bytes.length - 1,
  );
  if (bytes.length > 0 && capped.scan.verdict !== "fail") {
    console.error(`${path.basename(file)}: a stream over the cap passed`);
    failed = true;
  }

  const manifest = scan.manifest;
  const sig = manifest
    ? await checkArchiveSignature(scan.files, scan.hashes, manifest.name ? slugOf(file) : "", manifest.version)
    : { state: "absent" };
  console.log(
    `${path.basename(file)}: ${scan.verdict}, ${(bytes.length / 2 ** 20).toFixed(1)} MiB, ` +
      `${scan.containerCount} container(s), signature ${sig.state}` +
      ("message" in sig && sig.message ? ` (${sig.message})` : "") +
      `, heap +${(peak / 2 ** 20).toFixed(0)} MiB`,
  );
  for (const f of scan.findings) console.log(`  ${f.level} ${f.code}: ${f.message}`);
}

/** The slug a pack was published as: its file name before the version. */
function slugOf(file: string): string {
  return path.basename(file).replace(/-\d+\.\d+\.\d+(-[\w.]+)?\.mjolnir$/, "");
}

process.exit(failed ? 1 : 0);
