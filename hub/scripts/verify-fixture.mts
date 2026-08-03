// Cross-implementation conformance check for author signatures.
//
// Feeds a fixture produced by `cargo run -p mjolnir-sign --example fixture`
// through the hub's own verifier. The editor signs in Rust and the hub
// accepts or rejects in TypeScript, so the two must agree exactly — a
// divergence would reject every honest upload, which matters a great deal
// once REQUIRE_SIGNED_UPLOADS is on.
//
//   cargo run -q -p mjolnir-sign --example fixture > fixture.json
//   npx tsx scripts/verify-fixture.mts fixture.json

import { readFileSync } from "node:fs";

import { checkArchiveSignature, SIGNATURE_MEMBER } from "../src/lib/api/signing";

interface Fixture {
  slug: string;
  version: string;
  fingerprint: string;
  envelope: string;
  members: Record<string, string>;
}

const path = process.argv[2];
if (!path) {
  console.error("usage: tsx scripts/verify-fixture.mts <fixture.json>");
  process.exit(2);
}
const fixture: Fixture = JSON.parse(readFileSync(path, "utf8"));

function archive(members: Record<string, string>): Record<string, Uint8Array> {
  const files: Record<string, Uint8Array> = {
    [SIGNATURE_MEMBER]: new TextEncoder().encode(fixture.envelope),
  };
  for (const [name, b64] of Object.entries(members)) {
    files[name] = Uint8Array.from(Buffer.from(b64, "base64"));
  }
  return files;
}

let failures = 0;
const check = async (
  what: string,
  files: Record<string, Uint8Array>,
  expect: "valid" | "invalid",
  slug = fixture.slug,
  version = fixture.version,
) => {
  const result = await checkArchiveSignature(files, slug, version);
  const ok = result.state === expect;
  if (!ok) failures++;
  const detail =
    result.state === "invalid" ? ` (${result.message})` : result.state === "valid" ? "" : "";
  console.log(`${ok ? "ok  " : "FAIL"}  ${what}: ${result.state}${detail}`);
  return result;
};

// The signature a real Rust signer produced must verify here.
const valid = await check("rust-signed archive verifies", archive(fixture.members), "valid");
if (valid.state === "valid" && valid.signature.fingerprint !== fixture.fingerprint) {
  failures++;
  console.log(
    `FAIL  fingerprint mismatch: rust ${fixture.fingerprint}, ts ${valid.signature.fingerprint}`,
  );
} else if (valid.state === "valid") {
  console.log(`ok    fingerprint agrees: ${valid.signature.fingerprint.slice(0, 16)}…`);
}

// And the tamper cases must be caught, exactly as the Rust side catches them.
const tampered = archive(fixture.members);
const firstContainer = Object.keys(fixture.members).find((n) => n.startsWith("content/"))!;
tampered[firstContainer] = Uint8Array.from([...tampered[firstContainer]].map((b, i) => (i === 0 ? b ^ 0xff : b)));
await check("flipped container byte rejected", tampered, "invalid");

const added = archive(fixture.members);
added["content/extra.utoc"] = Uint8Array.from([1]);
await check("added member rejected", added, "invalid");

const removed = archive(fixture.members);
delete removed[firstContainer];
await check("removed member rejected", removed, "invalid");

await check("wrong slug rejected", archive(fixture.members), "invalid", "other-mod");
await check("wrong version rejected", archive(fixture.members), "invalid", fixture.slug, "9.9.9");

const unsigned = archive(fixture.members);
delete unsigned[SIGNATURE_MEMBER];
await check("unsigned archive reports absent", unsigned, "absent" as "valid");

console.log(failures === 0 ? "\nconformance: PASS" : `\nconformance: ${failures} FAILURE(S)`);
process.exit(failures === 0 ? 0 : 1);
