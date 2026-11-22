/**
 * Semantic search over the docs: sections found by what they mean.
 *
 * The docs palette ranks keywords in the browser (src/lib/docs-search.ts),
 * which is right for a name and wrong for a question: "how do I stop a host
 * leaving from ending the match" shares no rare word with the section that
 * answers it. Here the same chunks are embedded with Workers AI and held in a
 * Vectorize index; a query is embedded and its nearest chunks returned as
 * keys, which the palette fuses with its own ranking.
 *
 * Two bindings, both optional: `AI` and `DOCS_INDEX` (wrangler.jsonc). Without
 * them, and whenever either fails, the search answers `semantic: false` and
 * the palette stays on keywords. Nothing here is on the path of a page render.
 *
 * The index is filled from the deployed site's own /docs-search.json by
 * POST /docs/search/sync, which deploy-hub.yml calls after a deploy. Vectorize
 * keeps only a vector and a key per chunk: the text stays in the static file.
 * Vectorize applies writes a minute or two after it accepts them (measured
 * 2026-11-21), so a search right after a sync still sees the build before, and
 * a second sync in that window repeats the first. Both are harmless.
 */
import { createRoute, z, type OpenAPIHono } from "@hono/zod-openapi";

import { chunkKeys, type SearchIndexFile } from "../docs-search";
import { authenticate, rateLimit } from "./auth";
import type { ApiEnv } from "./bindings";
import { ErrorSchema } from "./schemas";

/**
 * The embedding model, and the index's dimensions with it: an index is made
 * for one size and cannot change it. Changing this means a new index
 * (`wrangler vectorize create … --dimensions`), not an edit here alone.
 */
export const EMBEDDING_MODEL = "@cf/baai/bge-m3";

/**
 * What bge-m3's cosine similarity means for these docs, measured on the filled
 * index on 2026-11-21. A question the docs answer puts its section at 0.58 to
 * 0.72; questions about nothing here ("best pizza toppings", "python list
 * comprehension") top out at 0.40 to 0.48. So similarity is rescaled to a
 * relevance of 0 at SIMILARITY_FLOOR and 1 at SIMILARITY_STRONG, and a chunk
 * under MIN_RELEVANCE is not returned: the nearest chunk to an unanswerable
 * question is not an answer. Another model has another scale; re-measure.
 */
const SIMILARITY_FLOOR = 0.5;
const SIMILARITY_STRONG = 0.7;
const MIN_RELEVANCE = 0.1;

/** The record that says which build the index holds. Never a search result. */
const STATE_ID = "state";
const MAX_QUERY_CHARS = 200;
const TOP_K = 24;
/** Texts per embedding call, and calls in flight at once. */
const EMBED_BATCH = 32;
const EMBED_PARALLEL = 4;
/** Vectorize takes at most 1000 vectors a call from a Worker. */
const UPSERT_BATCH = 500;
/** How long one query's answer is kept at the edge. */
const CACHE_SECONDS = 600;

type Env = ApiEnv["Bindings"];
type Ready = Env & Required<Pick<Env, "AI" | "DOCS_INDEX">>;

function ready(env: Env): env is Ready {
  return Boolean(env.AI && env.DOCS_INDEX);
}

async function embed(env: Ready, texts: string[]): Promise<number[][]> {
  const out = await env.AI.run(EMBEDDING_MODEL, { text: texts, truncate_inputs: true });
  const data = "data" in out ? out.data : undefined;
  if (!data || data.length !== texts.length) {
    throw new Error(`${EMBEDDING_MODEL} returned ${data?.length ?? 0} embeddings for ${texts.length} texts`);
  }
  return data;
}

/** The edge cache, where there is one: not under `next dev`. */
function edgeCache(): Cache | undefined {
  return (globalThis as { caches?: { default?: Cache } }).caches?.default;
}

const SearchSchema = z
  .object({
    semantic: z.boolean().openapi({
      description: "False when this deployment has no semantic index, or it failed: use keyword results alone.",
    }),
    hits: z.array(
      z.object({
        key: z.string().openapi({ example: "sound-mixer#what-it-changes#0", description: "doc slug, heading anchor, part" }),
        score: z.number().openapi({ description: "Cosine similarity of the section to the query." }),
        relevance: z.number().openapi({
          description: "The similarity on a 0 to 1 scale, 1 being a strong match. Sections below 0.1 are left out.",
        }),
      }),
    ),
  })
  .openapi("DocsSearch");

const SyncSchema = z
  .object({
    status: z.enum(["current", "indexed"]),
    build: z.string(),
    chunks: z.number().int(),
  })
  .openapi("DocsSearchSync");

export function registerDocsSearchRoutes(app: OpenAPIHono<ApiEnv>) {
  app.openapi(
    createRoute({
      method: "get",
      path: "/docs/search",
      tags: ["docs"],
      summary: "Find docs sections by meaning",
      description:
        "Embeds `q` and returns the nearest sections of the published docs, best first, as keys into " +
        "/docs-search.json (`slug#anchor#part`). The docs search palette merges these with its own " +
        "keyword ranking. Answers `semantic: false` with no hits when the deployment has no semantic index.",
      request: {
        query: z.object({ q: z.string().openapi({ example: "how do I add bots to my map" }) }),
      },
      responses: {
        200: { description: "Hits, or none.", content: { "application/json": { schema: SearchSchema } } },
      },
    }),
    async (c) => {
      const q = c.req.valid("query").q.trim().replace(/\s+/g, " ").slice(0, MAX_QUERY_CHARS);
      const env = c.env;
      if (q.length < 3 || !ready(env)) return c.json({ semantic: false, hits: [] }, 200);

      // Keyed on the query alone. An answer a deploy has made stale names
      // chunks by key, and the palette skips a key its build does not have.
      const cache = edgeCache();
      const cacheKey = new Request(new URL(`/api/v1/docs/search?q=${encodeURIComponent(q.toLowerCase())}`, c.req.url));
      const cached = await cache?.match(cacheKey);
      if (cached) return cached as never;

      try {
        const [vector] = await embed(env, [q]);
        const found = await env.DOCS_INDEX.query(vector, { topK: TOP_K, returnMetadata: "all" });
        const hits = found.matches
          .filter((match) => match.id !== STATE_ID && typeof match.metadata?.k === "string")
          .map((match) => ({
            key: match.metadata!.k as string,
            score: match.score,
            relevance: Math.min(
              1,
              Math.max(0, (match.score - SIMILARITY_FLOOR) / (SIMILARITY_STRONG - SIMILARITY_FLOOR)),
            ),
          }))
          .filter((hit) => hit.relevance >= MIN_RELEVANCE);
        const response = c.json({ semantic: true, hits }, 200, {
          "Cache-Control": `public, max-age=${CACHE_SECONDS}`,
        });
        if (cache) c.executionCtx.waitUntil(cache.put(cacheKey, response.clone()));
        return response;
      } catch (error) {
        console.error("docs search: semantic query failed", error);
        return c.json({ semantic: false, hits: [] }, 200);
      }
    },
  );

  app.openapi(
    createRoute({
      method: "post",
      path: "/docs/search/sync",
      tags: ["docs"],
      summary: "Bring the semantic index up to the deployed docs",
      description:
        "Reads this deployment's /docs-search.json and, when the semantic index holds another build, " +
        "embeds every chunk, replaces the index's contents and removes what is left of the old build. " +
        "A no-op when the index is current. Takes no body and no credentials: the content comes from the " +
        "deployment, never the caller, so all a caller chooses is when. Reindexes by callers who are not " +
        "admins share a small hourly budget. Called by the deploy workflow after each deploy.",
      responses: {
        200: { description: "The index holds this build.", content: { "application/json": { schema: SyncSchema } } },
        429: { description: "Too many syncs this hour.", content: { "application/json": { schema: ErrorSchema } } },
        500: { description: "The sync failed part way; calling again resumes it.", content: { "application/json": { schema: ErrorSchema } } },
        503: { description: "This deployment has no semantic index.", content: { "application/json": { schema: ErrorSchema } } },
      },
    }),
    async (c) => {
      const env = c.env;
      if (!ready(env)) {
        return c.json({ error: "not_configured", message: "No AI or DOCS_INDEX binding." }, 503);
      }
      try {
        const source = new Request(new URL("/docs-search.json", c.req.url));
        const fetched = await (env.ASSETS ? env.ASSETS.fetch(source as never) : fetch(source));
        if (!fetched.ok) throw new Error(`/docs-search.json answered ${fetched.status}`);
        const file = (await fetched.json()) as SearchIndexFile;

        const [state] = await env.DOCS_INDEX.getByIds([STATE_ID]);
        const held = state?.metadata as { build?: string; count?: number; model?: string } | undefined;
        if (held?.build === file.build && held.model === EMBEDDING_MODEL) {
          return c.json({ status: "current" as const, build: file.build, chunks: file.chunks.length }, 200);
        }

        // Only a reindex spends the budget: asking whether the index is
        // current costs one read, and must not starve the sync after a deploy.
        const auth = await authenticate(c);
        if (auth?.user.role !== "admin" && !(await rateLimit(c, "anyone", "docs-search-sync", 6))) {
          return c.json({ error: "rate_limited" }, 429);
        }

        const keys = chunkKeys(file);
        const texts = file.chunks.map(([doc, , heading, text]) =>
          [file.docs[doc][2], heading, text].filter(Boolean).join("\n"),
        );
        const { dimensions } = await env.DOCS_INDEX.describe();

        // Position is the id: a build's chunk 12 overwrites the last build's
        // chunk 12, and what the last build had beyond this one's count is
        // deleted below. The key in the metadata is what a search returns.
        const batches: number[] = [];
        for (let at = 0; at < texts.length; at += EMBED_BATCH) batches.push(at);
        const vectors: Array<{ id: string; values: number[]; metadata: { k: string } }> = new Array(texts.length);
        for (let at = 0; at < batches.length; at += EMBED_PARALLEL) {
          await Promise.all(
            batches.slice(at, at + EMBED_PARALLEL).map(async (start) => {
              const values = await embed(env, texts.slice(start, start + EMBED_BATCH));
              values.forEach((value, offset) => {
                if (value.length !== dimensions) {
                  throw new Error(
                    `${EMBEDDING_MODEL} embeds to ${value.length} dimensions and the index was made for ${dimensions}`,
                  );
                }
                vectors[start + offset] = { id: `c${start + offset}`, values: value, metadata: { k: keys[start + offset] } };
              });
            }),
          );
        }
        for (let at = 0; at < vectors.length; at += UPSERT_BATCH) {
          await env.DOCS_INDEX.upsert(vectors.slice(at, at + UPSERT_BATCH));
        }

        const stale: string[] = [];
        for (let id = vectors.length; id < (held?.count ?? 0); id += 1) stale.push(`c${id}`);
        for (let at = 0; at < stale.length; at += UPSERT_BATCH) {
          await env.DOCS_INDEX.deleteByIds(stale.slice(at, at + UPSERT_BATCH));
        }

        // Last, so a sync that stopped part way is not taken for a finished one.
        const marker = new Array<number>(dimensions).fill(0);
        marker[0] = 1;
        await env.DOCS_INDEX.upsert([
          { id: STATE_ID, values: marker, metadata: { build: file.build, count: vectors.length, model: EMBEDDING_MODEL } },
        ]);
        return c.json({ status: "indexed" as const, build: file.build, chunks: vectors.length }, 200);
      } catch (error) {
        console.error("docs search: sync failed", error);
        return c.json({ error: "sync_failed", message: error instanceof Error ? error.message : String(error) }, 500);
      }
    },
  );
}
