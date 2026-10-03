/**
 * Mounts the Hono API (src/lib/api/app.ts) under /api/v1.
 *
 * Everything API-shaped lives in the Hono app — this file only bridges
 * Next's route handler convention to it and hands over the Worker env.
 */
import { getCloudflareContext } from "@opennextjs/cloudflare";

import { app } from "@/lib/api/app";

const handle = async (req: Request): Promise<Response> => {
  const { env, ctx, cf } = getCloudflareContext();
  // Next hands over a plain Request: Cloudflare's view of the caller (colo,
  // country, coordinates) rides on the Worker's own request only. The lobby
  // browser estimates ping from it (src/lib/api/lobby.ts, whereFrom).
  if (cf && !(req as { cf?: unknown }).cf) {
    Object.defineProperty(req, "cf", { value: cf });
  }
  return app.fetch(req, env as never, ctx as never);
};

export {
  handle as GET,
  handle as POST,
  handle as PUT,
  handle as PATCH,
  handle as DELETE,
  handle as OPTIONS,
};
