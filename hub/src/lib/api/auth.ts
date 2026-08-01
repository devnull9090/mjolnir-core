/**
 * Discord OAuth and cookie sessions.
 *
 * Flow: `/auth/discord` sets a random state cookie and redirects to Discord;
 * the callback checks the state, exchanges the code, upserts the user in D1,
 * and sets an HttpOnly JWT session cookie. No token or secret ever reaches
 * the browser.
 *
 * The redirect URI is derived from the request origin, so the same code
 * serves localhost and production — both URIs must be registered in the
 * Discord application's OAuth2 settings.
 */
import type { Context } from "hono";
import { getCookie, setCookie, deleteCookie } from "hono/cookie";

import type { ApiEnv, SessionUser } from "./bindings";
import { signSession, verifySession } from "./jwt";

const SESSION_COOKIE = "mj_session";
const STATE_COOKIE = "mj_oauth_state";
const DISCORD_API = "https://discord.com/api/v10";

type Ctx = Context<ApiEnv>;

function jwtSecret(c: Ctx): string | undefined {
  // process.env first: OpenNext mirrors string secrets there in every mode.
  return process.env.JWT_SECRET ?? c.env.JWT_SECRET;
}

function discordCreds(c: Ctx): { id: string; secret: string } | null {
  const id = process.env.DISCORD_CLIENT_ID ?? c.env.DISCORD_CLIENT_ID;
  const secret = process.env.DISCORD_CLIENT_SECRET ?? c.env.DISCORD_CLIENT_SECRET;
  return id && secret ? { id, secret } : null;
}

function redirectUri(c: Ctx): string {
  return new URL("/api/v1/auth/discord/callback", c.req.url).toString();
}

/** Only same-site paths make valid post-login destinations. */
function safeNext(next: string | undefined): string {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/";
}

// ── Handlers ──────────────────────────────────────────────────────────

export async function loginRedirect(c: Ctx) {
  const creds = discordCreds(c);
  if (!creds) return c.json({ error: "oauth_unconfigured" }, 500);

  const state = crypto.randomUUID();
  const next = safeNext(c.req.query("next"));
  setCookie(c, STATE_COOKIE, `${state}|${next}`, {
    httpOnly: true,
    secure: true,
    sameSite: "Lax",
    path: "/api/v1/auth",
    maxAge: 600,
  });

  const url = new URL("https://discord.com/oauth2/authorize");
  url.searchParams.set("client_id", creds.id);
  url.searchParams.set("response_type", "code");
  url.searchParams.set("scope", "identify");
  url.searchParams.set("redirect_uri", redirectUri(c));
  url.searchParams.set("state", state);
  return c.redirect(url.toString(), 302);
}

export async function loginCallback(c: Ctx) {
  const creds = discordCreds(c);
  const secret = jwtSecret(c);
  if (!creds || !secret) return c.json({ error: "oauth_unconfigured" }, 500);

  const code = c.req.query("code");
  const state = c.req.query("state");
  const stateCookie = getCookie(c, STATE_COOKIE);
  deleteCookie(c, STATE_COOKIE, { path: "/api/v1/auth" });

  const [expectedState, next] = (stateCookie ?? "").split("|");
  if (!code || !state || !expectedState || state !== expectedState) {
    return c.json({ error: "bad_state", message: "OAuth state mismatch; try again." }, 400);
  }

  // Code → access token.
  const tokenRes = await fetch(`${DISCORD_API}/oauth2/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      client_id: creds.id,
      client_secret: creds.secret,
      grant_type: "authorization_code",
      code,
      redirect_uri: redirectUri(c),
    }),
  });
  if (!tokenRes.ok) {
    return c.json({ error: "token_exchange_failed" }, 502);
  }
  const token = (await tokenRes.json()) as { access_token?: string };
  if (!token.access_token) return c.json({ error: "token_exchange_failed" }, 502);

  // Token → identity.
  const meRes = await fetch(`${DISCORD_API}/users/@me`, {
    headers: { Authorization: `Bearer ${token.access_token}` },
  });
  if (!meRes.ok) return c.json({ error: "identity_fetch_failed" }, 502);
  const me = (await meRes.json()) as {
    id: string;
    username: string;
    global_name: string | null;
    avatar: string | null;
  };

  // Upsert; a returning user keeps their id, role and display_name.
  const row = await c.env.DB.prepare(
    `INSERT INTO users (id, discord_id, discord_username, discord_avatar, display_name)
     VALUES (?1, ?2, ?3, ?4, ?5)
     ON CONFLICT(discord_id) DO UPDATE SET
       discord_username = excluded.discord_username,
       discord_avatar = excluded.discord_avatar,
       updated_at = datetime('now')
     RETURNING id, banned_at`,
  )
    .bind(crypto.randomUUID(), me.id, me.username, me.avatar, me.global_name ?? me.username)
    .first<{ id: string; banned_at: string | null }>();

  if (!row) return c.json({ error: "user_upsert_failed" }, 500);
  if (row.banned_at) return c.json({ error: "banned" }, 403);

  const jwt = await signSession({ sub: row.id, did: me.id }, secret);
  setCookie(c, SESSION_COOKIE, jwt, {
    httpOnly: true,
    secure: true,
    sameSite: "Lax",
    path: "/",
    maxAge: 7 * 24 * 60 * 60,
  });
  return c.redirect(safeNext(next), 302);
}

export async function logout(c: Ctx) {
  deleteCookie(c, SESSION_COOKIE, { path: "/" });
  return c.json({ ok: true }, 200);
}

// ── Session lookup ────────────────────────────────────────────────────

/** Resolve the session cookie to a fresh user row; null when signed out. */
export async function sessionUser(c: Ctx): Promise<SessionUser | null> {
  const secret = jwtSecret(c);
  const token = getCookie(c, SESSION_COOKIE);
  if (!secret || !token) return null;
  const claims = await verifySession(token, secret);
  if (!claims) return null;

  const user = await c.env.DB.prepare(
    `SELECT id, discord_id, discord_username, discord_avatar, display_name,
            role, trust_level, created_at, banned_at
     FROM users WHERE id = ?1`,
  )
    .bind(claims.sub)
    .first<SessionUser & { banned_at: string | null }>();

  if (!user || user.banned_at) return null;
  return user;
}
