/**
 * Sign a mods release manifest with the Ed25519 release key.
 *
 * Usage: node scripts/sign-manifest.mjs <manifest.json> <out.sig>
 * The private key arrives via MODS_SIGNING_KEY (PKCS#8 PEM) — a GitHub
 * Actions secret, never a file in the repo. The matching public key is
 * committed at keys/mod-signing.pub; the launcher pins it and refuses any
 * mods manifest whose signature does not verify.
 *
 * Also verifies its own output against the committed public key before
 * exiting, so a key mismatch fails the release instead of shipping
 * artifacts nothing can install.
 */
import { createPrivateKey, createPublicKey, sign, verify } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const [manifestPath, sigPath] = process.argv.slice(2);
if (!manifestPath || !sigPath) {
  console.error("usage: node sign-manifest.mjs <manifest.json> <out.sig>");
  process.exit(2);
}
const pem = process.env.MODS_SIGNING_KEY;
if (!pem) {
  console.error("MODS_SIGNING_KEY is not set");
  process.exit(2);
}

const manifest = readFileSync(manifestPath);
const key = createPrivateKey(pem);
const signature = sign(null, manifest, key); // Ed25519: algorithm must be null
writeFileSync(sigPath, signature.toString("base64") + "\n");

const pubPem = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "..", "keys", "mod-signing.pub"),
);
const ok = verify(null, manifest, createPublicKey(pubPem), signature);
if (!ok) {
  console.error("FATAL: signature does not verify against keys/mod-signing.pub");
  process.exit(1);
}
console.log(`signed ${manifestPath} -> ${sigPath} (verified against committed public key)`);
