/**
 * Bindings from wrangler.jsonc plus deployed secrets, as seen by
 * getCloudflareContext(). Keep in step with src/lib/api/bindings.ts.
 */
import type { D1Database, R2Bucket } from "@cloudflare/workers-types";

declare global {
  interface CloudflareEnv {
    DB: D1Database;
    MODS_BUCKET: R2Bucket;
    RELEASES_BUCKET: R2Bucket;
    SITE_URL: string;
    DISCORD_CLIENT_ID?: string;
    DISCORD_CLIENT_SECRET?: string;
    DISCORD_PUBLIC_KEY?: string;
    JWT_SECRET?: string;
  }
}

export {};
