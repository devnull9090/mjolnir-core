import type { NextConfig } from "next";
import { initOpenNextCloudflareForDev } from "@opennextjs/cloudflare";

// Makes getCloudflareContext() work under `next dev`: bindings come from
// wrangler.jsonc (local D1/R2 simulations) and secrets from .dev.vars.
initOpenNextCloudflareForDev();

const nextConfig: NextConfig = {
  async headers() {
    return [
      {
        // The sitemap lists mods out of D1, so it cannot be prerendered and
        // is now built per request. This puts the edge cache in front of it:
        // a crawler's fetch costs two D1 reads an hour, not two per hit.
        source: "/sitemap.xml",
        headers: [
          {
            key: "Cache-Control",
            value: "public, max-age=0, s-maxage=3600, stale-while-revalidate=86400",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
