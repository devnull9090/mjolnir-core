/**
 * Minimal HS256 JWT over WebCrypto — edge-safe, zero dependencies.
 *
 * Only what sessions need: sign with a TTL, verify signature + expiry.
 * Verification uses `crypto.subtle.verify`, so signature comparison is
 * constant-time by construction.
 */

const encoder = new TextEncoder();

export interface SessionClaims {
  /** Hub user id (users.id). */
  sub: string;
  /** Discord snowflake, for display and re-auth checks. */
  did: string;
  iat: number;
  exp: number;
}

function b64url(bytes: Uint8Array): string {
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function b64urlDecode(s: string): Uint8Array | null {
  try {
    const padded = s.replace(/-/g, "+").replace(/_/g, "/");
    const raw = atob(padded);
    const out = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
    return out;
  } catch {
    return null;
  }
}

async function hmacKey(secret: string, usage: KeyUsage): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    [usage],
  );
}

export async function signSession(
  claims: Pick<SessionClaims, "sub" | "did">,
  secret: string,
  ttlSeconds: number = 7 * 24 * 60 * 60,
): Promise<string> {
  const now = Math.floor(Date.now() / 1000);
  const payload: SessionClaims = { ...claims, iat: now, exp: now + ttlSeconds };
  const head = b64url(encoder.encode(JSON.stringify({ alg: "HS256", typ: "JWT" })));
  const body = b64url(encoder.encode(JSON.stringify(payload)));
  const key = await hmacKey(secret, "sign");
  const sig = await crypto.subtle.sign("HMAC", key, encoder.encode(`${head}.${body}`));
  return `${head}.${body}.${b64url(new Uint8Array(sig))}`;
}

/** Returns the claims when the token is authentic and unexpired, else null. */
export async function verifySession(token: string, secret: string): Promise<SessionClaims | null> {
  const parts = token.split(".");
  if (parts.length !== 3) return null;
  const [head, body, sig] = parts;

  const sigBytes = b64urlDecode(sig);
  if (!sigBytes) return null;
  const key = await hmacKey(secret, "verify");
  const ok = await crypto.subtle.verify(
    "HMAC",
    key,
    sigBytes as BufferSource,
    encoder.encode(`${head}.${body}`),
  );
  if (!ok) return null;

  const payloadBytes = b64urlDecode(body);
  if (!payloadBytes) return null;
  let claims: SessionClaims;
  try {
    claims = JSON.parse(new TextDecoder().decode(payloadBytes));
  } catch {
    return null;
  }
  if (typeof claims.sub !== "string" || typeof claims.exp !== "number") return null;
  if (claims.exp <= Math.floor(Date.now() / 1000)) return null;
  return claims;
}
