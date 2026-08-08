import { NextResponse } from "next/server";

import { getInstallableTools, type ToolRelease } from "@/lib/tools";

/**
 * The current build of every tool the launcher can install.
 *
 * Each tool publishes `latest/manifest.json` beside its binary — the same
 * contract `apps/launcher/src-tauri/src/tools.rs` reads — carrying the
 * version, the download URL and the SHA-256 the launcher checks the bytes
 * against. Reading it here rather than in the page keeps a CDN outage out of
 * the render path: the page already names a version from the changelog, and
 * this only adds the hash and the size on top.
 */

export const revalidate = 300;

type Manifest = {
  version?: string;
  exe?: string;
  url?: string;
  sha256?: string;
  size?: number;
};

export async function GET() {
  const tools = await Promise.all(
    getInstallableTools().map(async (tool): Promise<ToolRelease> => {
      const base = tool.releaseBase!;
      const empty = {
        id: tool.slug,
        version: null,
        exe: null,
        url: null,
        sha256: null,
        size: null,
        checksums_url: `${base}/latest/checksums.txt`,
      };
      try {
        const res = await fetch(`${base}/latest/manifest.json`, {
          next: { revalidate },
        });
        if (!res.ok) {
          return { ...empty, error: `Manifest returned ${res.status}` };
        }
        const manifest = (await res.json()) as Manifest;
        return {
          id: tool.slug,
          version: manifest.version ?? null,
          exe: manifest.exe ?? null,
          url: manifest.url ?? null,
          sha256: manifest.sha256 ?? null,
          size: typeof manifest.size === "number" ? manifest.size : null,
          checksums_url: `${base}/latest/checksums.txt`,
          error: null,
        };
      } catch (err) {
        console.error(`Failed to read the ${tool.slug} manifest:`, err);
        return { ...empty, error: "Could not reach the release CDN" };
      }
    }),
  );

  return NextResponse.json({ tools });
}
