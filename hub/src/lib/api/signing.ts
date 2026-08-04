/**
 * Author-signature verification for uploaded archives.
 *
 * The TypeScript mirror of `crates/mjolnir-sign`: same envelope, same domain
 * prefix, same order — crypto first, parsing second, business checks last.
 * This module does the self-contained part (is the signature internally
 * valid for exactly these bytes?); binding the key to the uploading account
 * happens in publish.ts against the user_keys registry, because identity is
 * a database question, not a cryptographic one.
 *
 * Design and threat model: docs/mod_signing_design.md.
 */

export const SIGNATURE_MEMBER = "signature.json";
const PAYLOAD_TYPE = "mjolnir-mod-statement-v1";
const DOMAIN_PREFIX = "MJOLNIR-MOD-STATEMENT-V1\n";

/** DER prefix that wraps a raw 32-byte Ed25519 key into SPKI, the import
 *  format the runtime accepts everywhere (same path codesync.ts uses). */
const SPKI_PREFIX = new Uint8Array([
  0x30, 0x2a, 0x30, 0x05, 0x06, 0x03, 0x2b, 0x65, 0x70, 0x03, 0x21, 0x00,
]);

export interface VerifiedSignature {
  /** Lowercase hex sha256 of the raw public key. */
  fingerprint: string;
  /** The account the statement claims, when it claims one. */
  authorId: string | null;
  authorUsername: string | null;
  signedAt: string;
}

export type SignatureCheck =
  | { state: "absent" }
  | { state: "invalid"; message: string }
  | { state: "valid"; signature: VerifiedSignature };

function b64decode(text: string): Uint8Array | null {
  try {
    const raw = atob(text.trim());
    const out = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
    return out;
  } catch {
    return null;
  }
}

async function sha256HexBytes(bytes: Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", bytes as BufferSource);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export async function fingerprintOf(publicKey: Uint8Array): Promise<string> {
  return sha256HexBytes(publicKey);
}

async function verifyEd25519(
  publicKey: Uint8Array,
  message: Uint8Array,
  signature: Uint8Array,
): Promise<boolean> {
  try {
    const spki = new Uint8Array(SPKI_PREFIX.length + publicKey.length);
    spki.set(SPKI_PREFIX);
    spki.set(publicKey, SPKI_PREFIX.length);
    const key = await crypto.subtle.importKey(
      "spki",
      spki as BufferSource,
      { name: "Ed25519" },
      false,
      ["verify"],
    );
    return await crypto.subtle.verify(
      "Ed25519",
      key,
      signature as BufferSource,
      message as BufferSource,
    );
  } catch {
    return false;
  }
}

/**
 * Verify the archive's signature member against the release it is supposed
 * to describe. `files` is the unzipped archive (from the scanner's pass —
 * the archive is never unzipped twice).
 */
export async function checkArchiveSignature(
  files: Record<string, Uint8Array>,
  expectedSlug: string,
  expectedVersion: string,
): Promise<SignatureCheck> {
  const raw = files[SIGNATURE_MEMBER];
  if (!raw) return { state: "absent" };
  const bad = (message: string): SignatureCheck => ({ state: "invalid", message });

  let envelope: {
    schema_version?: number;
    payload_type?: string;
    payload?: string;
    public_key?: string;
    signature?: string;
  };
  try {
    envelope = JSON.parse(new TextDecoder().decode(raw));
  } catch {
    return bad("signature.json is not valid JSON.");
  }
  if (envelope.schema_version !== 1 || envelope.payload_type !== PAYLOAD_TYPE) {
    return bad(`Unsupported signature envelope (${envelope.payload_type} v${envelope.schema_version}).`);
  }
  const payload = b64decode(envelope.payload ?? "");
  const publicKey = b64decode(envelope.public_key ?? "");
  const signature = b64decode(envelope.signature ?? "");
  if (!payload || !publicKey || !signature) return bad("Envelope fields are not valid base64.");
  if (publicKey.length !== 32) return bad("public_key is not 32 bytes.");
  if (signature.length !== 64) return bad("signature is not 64 bytes.");

  // Crypto before parsing: nothing downstream sees unauthenticated bytes.
  const prefix = new TextEncoder().encode(DOMAIN_PREFIX);
  const message = new Uint8Array(prefix.length + payload.length);
  message.set(prefix);
  message.set(payload, prefix.length);
  if (!(await verifyEd25519(publicKey, message, signature))) {
    return bad("Signature does not verify.");
  }

  let statement: {
    schema_version?: number;
    slug?: string;
    version?: string;
    author?: { id?: string; username?: string } | null;
    key_fingerprint?: string;
    signed_at?: string;
    files?: Record<string, string>;
  };
  try {
    statement = JSON.parse(new TextDecoder().decode(payload));
  } catch {
    return bad("Signed statement does not parse.");
  }
  if (statement.schema_version !== 1 || typeof statement.files !== "object" || !statement.files) {
    return bad("Signed statement has an unsupported shape.");
  }
  const fingerprint = await fingerprintOf(publicKey);
  if (statement.key_fingerprint !== fingerprint) {
    return bad("Statement names a different key than the one that signed it.");
  }
  if (statement.slug !== expectedSlug || statement.version !== expectedVersion) {
    return bad(
      `Signature is for ${statement.slug} ${statement.version}, not ${expectedSlug} ${expectedVersion}.`,
    );
  }

  // Member-set equality, then per-member digests. Directory entries (name
  // ending "/") are not members; everything else is, including empty files —
  // the signer never writes empties, so an added one fails set equality.
  const actual = new Map<string, Uint8Array>();
  for (const [name, data] of Object.entries(files)) {
    if (name === SIGNATURE_MEMBER || name.endsWith("/")) continue;
    actual.set(name, data);
  }
  for (const path of Object.keys(statement.files)) {
    if (!actual.has(path)) return bad(`Signed member ${path} is missing from the archive.`);
  }
  for (const [path, data] of actual) {
    const want = statement.files[path];
    if (!want) return bad(`Archive member ${path} is not covered by the signature.`);
    if ((await sha256HexBytes(data)) !== want) {
      return bad(`Archive member ${path} does not match its signature.`);
    }
  }

  return {
    state: "valid",
    signature: {
      fingerprint,
      authorId: statement.author?.id ?? null,
      authorUsername: statement.author?.username ?? null,
      signedAt: statement.signed_at ?? "",
    },
  };
}
