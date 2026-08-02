/**
 * Mirrors the signed code-mod set onto hub pages.
 *
 * Script and native mods never travel through open upload — they ship from
 * mjolnir-core CI as an Ed25519-signed manifest (release-mods.yml). This
 * module gives them hub pages anyway: POST /code-mods/sync fetches the
 * latest manifest, verifies the signature **server-side against the same
 * committed public key the launcher pins**, and upserts a mod + release row
 * per entry. Downloads redirect to the signed artifacts.
 *
 * The endpoint is deliberately public: the manifest signature is the
 * authority, not the caller, and the operation is idempotent. An attacker
 * who calls it achieves an up-to-date mirror.
 */
import type { OpenAPIHono } from "@hono/zod-openapi";
import { createRoute, z } from "@hono/zod-openapi";
import type { ApiEnv } from "./bindings";
import { rateLimit } from "./auth";
import { ErrorSchema } from "./schemas";

/**
 * SPKI DER of keys/mod-signing.pub, base64. Must match that file — the
 * launcher's test suite pins the file, and a mismatch here just makes every
 * sync fail verification loudly.
 */
const MOD_SIGNING_PUB_B64 = "MCowBQYDK2VwAyEArb2UhwU41NNYHenYf9BqL/QU3g5La7I+Qdih2ZJmEB4=";

const CODE_MODS_BASE = "https://releases.mjolnircore.com/mods";

/** The Discord-less identity that owns first-party script mod pages. */
const SYSTEM_DISCORD_ID = "system:mjolnir-core";

type EnvOverrides = { CODE_MODS_BASE?: string; CODE_MODS_PUB_B64?: string };

function base(env: EnvOverrides): string {
  return process.env.CODE_MODS_BASE ?? env.CODE_MODS_BASE ?? CODE_MODS_BASE;
}

function pubKeyB64(env: EnvOverrides): string {
  // Dev override so a local end-to-end test can use a throwaway pair;
  // production always verifies against the committed key.
  return process.env.CODE_MODS_PUB_B64 ?? env.CODE_MODS_PUB_B64 ?? MOD_SIGNING_PUB_B64;
}

const ManifestEntry = z.object({
  id: z.string().min(1),
  file: z.string(),
  sha256: z.string().length(64),
  size: z.number().int(),
  url: z.string().url(),
  version: z.string().default("0.0.0"),
  summary: z.string().optional(),
  category: z.string().default("tools"),
  /** Explicit hub slug; derived from the id when absent. */
  slug: z.string().regex(/^[a-z0-9][a-z0-9-]{1,63}$/).optional(),
});

const SignedManifest = z.object({
  schema_version: z.literal(1),
  set_version: z.string(),
  mods: z.array(ManifestEntry),
});

function b64decode(s: string): Uint8Array {
  const raw = atob(s.replace(/\s+/g, ""));
  const out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}

async function verifySignature(env: EnvOverrides, manifest: Uint8Array, sigB64: string): Promise<boolean> {
  try {
    const key = await crypto.subtle.importKey(
      "spki",
      b64decode(pubKeyB64(env)) as BufferSource,
      { name: "Ed25519" },
      false,
      ["verify"],
    );
    return await crypto.subtle.verify(
      "Ed25519",
      key,
      b64decode(sigB64) as BufferSource,
      manifest as BufferSource,
    );
  } catch {
    return false;
  }
}

/** MJOLNIRFlyCam → mjolnir-flycam; MJOLNIRConsoleEnabler → mjolnir-console-enabler. */
export function slugForModId(id: string): string {
  const stripped = id.replace(/^MJOLNIR/, "");
  const kebab = stripped
    .replace(/([a-z0-9])([A-Z])/g, "$1-$2")
    .replace(/[^a-zA-Z0-9-]+/g, "-")
    .toLowerCase()
    .replace(/^-+|-+$/g, "");
  return `mjolnir-${kebab || "core"}`;
}

export function registerCodeSyncRoutes(app: OpenAPIHono<ApiEnv>) {
  app.openapi(
    createRoute({
      method: "post",
      path: "/code-mods/sync",
      tags: ["mods"],
      summary: "Mirror the signed code-mod set onto hub pages",
      description:
        "Fetches the latest signed release manifest, verifies its Ed25519 " +
        "signature against the platform's committed public key, and upserts " +
        "a hub mod page and release per entry. Idempotent; callable by " +
        "anyone because the signature, not the caller, is the authority. " +
        "CI calls it after every code-mods release.",
      responses: {
        200: {
          description: "What the sync did.",
          content: {
            "application/json": {
              schema: z
                .object({
                  set_version: z.string(),
                  mods_synced: z.number().int(),
                  releases_created: z.number().int(),
                })
                .openapi("CodeSyncResult"),
            },
          },
        },
        429: { description: "Slow down.", content: { "application/json": { schema: ErrorSchema } } },
        502: {
          description: "Manifest unreachable, unparseable, or its signature failed.",
          content: { "application/json": { schema: ErrorSchema } },
        },
      },
    }),
    async (c) => {
      if (!(await rateLimit(c, `ip:${c.req.header("cf-connecting-ip") ?? "local"}`, "codesync", 12))) {
        return c.json({ error: "rate_limited" }, 429);
      }

      const env = c.env as EnvOverrides;
      const [manifestRes, sigRes] = await Promise.all([
        fetch(`${base(env)}/latest/manifest.json`, { cf: { cacheTtl: 0 } } as RequestInit),
        fetch(`${base(env)}/latest/manifest.json.sig`, { cf: { cacheTtl: 0 } } as RequestInit),
      ]);
      if (!manifestRes.ok || !sigRes.ok) {
        return c.json({ error: "manifest_unavailable" }, 502);
      }
      const manifestBytes = new Uint8Array(await manifestRes.arrayBuffer());
      const sigB64 = (await sigRes.text()).trim();

      if (!(await verifySignature(env, manifestBytes, sigB64))) {
        return c.json(
          { error: "bad_signature", message: "Manifest signature failed verification; nothing synced." },
          502,
        );
      }

      let manifest;
      try {
        manifest = SignedManifest.parse(JSON.parse(new TextDecoder().decode(manifestBytes)));
      } catch {
        return c.json({ error: "bad_manifest" }, 502);
      }

      // The owning identity for first-party pages.
      const owner = await c.env.DB.prepare(
        `INSERT INTO users (id, discord_id, discord_username, display_name, role)
         VALUES (?1, ?2, 'mjolnir-core', 'MJOLNIR Core', 'admin')
         ON CONFLICT(discord_id) DO UPDATE SET updated_at = datetime('now')
         RETURNING id`,
      )
        .bind(crypto.randomUUID(), SYSTEM_DISCORD_ID)
        .first<{ id: string }>();
      if (!owner) return c.json({ error: "owner_upsert_failed" }, 502);

      let releasesCreated = 0;
      for (const entry of manifest.mods) {
        const slug = entry.slug ?? slugForModId(entry.id);
        const modId = crypto.randomUUID();
        await c.env.DB.prepare(
          `INSERT INTO mods (id, slug, name, summary, owner_id, type, category, status)
           VALUES (?1, ?2, ?3, ?4, ?5, 'script', ?6, 'published')
           ON CONFLICT(slug) DO UPDATE SET
             summary = excluded.summary,
             category = excluded.category,
             updated_at = datetime('now')`,
        )
          .bind(modId, slug, entry.id, entry.summary ?? null, owner.id, entry.category)
          .run();
        const mod = await c.env.DB.prepare(`SELECT id FROM mods WHERE slug = ?1`)
          .bind(slug)
          .first<{ id: string }>();
        if (!mod) continue;

        const inserted = await c.env.DB.prepare(
          `INSERT OR IGNORE INTO mod_releases
             (id, mod_id, version, channel, changelog_md, sha256, file_size, download_url, status)
           VALUES (?1, ?2, ?3, 'stable', ?4, ?5, ?6, ?7, 'published')`,
        )
          .bind(
            crypto.randomUUID(),
            mod.id,
            entry.version,
            `Shipped in signed set v${manifest.set_version}.`,
            entry.sha256,
            entry.size,
            entry.url,
          )
          .run();
        releasesCreated += inserted.meta.changes ?? 0;
      }

      return c.json(
        {
          set_version: manifest.set_version,
          mods_synced: manifest.mods.length,
          releases_created: releasesCreated,
        },
        200,
      );
    },
  );
}
