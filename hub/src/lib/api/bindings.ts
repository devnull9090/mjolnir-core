import type { D1Database, R2Bucket } from "@cloudflare/workers-types";

/**
 * Worker bindings and secrets the API runs against, matching wrangler.jsonc
 * and the secrets deploy-hub.yml uploads.
 *
 * Secrets are optional at the type level because local `next dev` reads them
 * from `.dev.vars` and a missing one should fail with a clear 500 at the
 * call site, not a type error masked by a non-null assertion.
 */
export interface HubBindings {
  DB: D1Database;
  MODS_BUCKET: R2Bucket;
  RELEASES_BUCKET: R2Bucket;
  SITE_URL: string;
  DISCORD_CLIENT_ID?: string;
  DISCORD_CLIENT_SECRET?: string;
  DISCORD_PUBLIC_KEY?: string;
  JWT_SECRET?: string;
}

/** Hono type parameter: bindings plus per-request variables. */
export type ApiEnv = {
  Bindings: HubBindings;
  Variables: {
    /** Set by the auth middleware when a valid session cookie is present. */
    user?: SessionUser;
  };
};

/** The user as carried in a session, loaded fresh from D1 per request. */
export interface SessionUser {
  id: string;
  discord_id: string;
  discord_username: string;
  discord_avatar: string | null;
  display_name: string | null;
  role: "user" | "moderator" | "admin";
  trust_level: number;
  created_at: string;
}
