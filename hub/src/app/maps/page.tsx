import Link from "next/link";
import type { Metadata } from "next";
import { Map as MapIcon, Upload } from "lucide-react";
import { getCloudflareContext } from "@opennextjs/cloudflare";

import { Navbar } from "../components/Navbar";
import { Footer } from "../components/Footer";
import { listMaps } from "@/lib/api/maps";
import { GAME_TYPE_NAMES } from "@/kit/types";
import type { MapListing } from "@/kit/types";

export const metadata: Metadata = {
  title: "Maps | MJOLNIR Core",
  description:
    "The classic Halo: Combat Evolved multiplayer maps, rebuilt for Halo Campaign Evolved, and maps from the community.",
};

const MODES = ["all", "slayer", "ctf", "team_slayer", "koth", "oddball"];

function sizeOf(bytes: number | null): string {
  if (!bytes) return "";
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function MapCard({ map }: { map: MapListing }) {
  return (
    <Link
      href={`/mods/${map.slug}`}
      className="group block bg-surface border border-border rounded-xl p-4 hover:border-gold/40 transition-colors"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-semibold text-foreground truncate">{map.title}</span>
        <span className="text-[11px] font-mono text-text-dim">{map.code}</span>
      </div>
      <p className="text-sm text-text-muted mt-1 line-clamp-2 min-h-[2.5rem]">
        {map.summary ?? "No summary."}
      </p>
      <div className="flex flex-wrap gap-1.5 mt-3">
        {map.modes.map((m) => (
          <span
            key={m}
            className="text-[11px] px-2 py-0.5 rounded-full bg-gold/10 text-gold border border-gold/20"
          >
            {GAME_TYPE_NAMES[m] ?? m}
          </span>
        ))}
      </div>
      <div className="flex items-center gap-3 mt-3 text-xs text-text-dim">
        {map.release ? <span>v{map.release.version}</span> : <span>no release yet</span>}
        {map.release?.file_size ? <span>{sizeOf(map.release.file_size)}</span> : null}
        {!map.official && <span className="truncate">by {map.owner}</span>}
      </div>
    </Link>
  );
}

export default async function MapsPage({
  searchParams,
}: {
  searchParams: Promise<{ mode?: string }>;
}) {
  const params = await searchParams;
  const mode = MODES.find((m) => m === params.mode) ?? "all";

  const { env } = getCloudflareContext();
  const maps = await listMaps(env.DB as never, { mode: mode === "all" ? undefined : mode });
  const official = maps.filter((m) => m.official);
  const community = maps.filter((m) => !m.official);

  return (
    <>
      <Navbar />

      <main className="pt-32 md:pt-36 pb-16 px-6 max-w-6xl mx-auto">
        <div className="mb-10 flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-4xl font-black text-foreground mb-3">Maps</h1>
            <p className="text-text-muted text-lg max-w-2xl">
              The classic Halo: Combat Evolved multiplayer maps, rebuilt for Halo Campaign
              Evolved, and maps from the community. The launcher installs them, and everything
              they need, in one click.
            </p>
          </div>
          <Link
            href="/docs/notes/map-distribution"
            className="flex items-center gap-2 px-4 py-2 text-sm font-semibold rounded-lg border border-border text-foreground hover:border-gold/40 transition-colors"
          >
            <Upload className="w-4 h-4" />
            Make a map
          </Link>
        </div>

        <div className="mb-8 flex flex-wrap items-center gap-1 text-xs">
          {MODES.map((m) => (
            <Link
              key={m}
              href={m === "all" ? "/maps" : `/maps?mode=${m}`}
              className={`px-3 py-1.5 rounded-full border transition-colors ${
                m === mode
                  ? "border-gold/60 text-gold bg-gold/10"
                  : "border-border text-text-muted hover:text-foreground"
              }`}
            >
              {m === "all" ? "All game types" : (GAME_TYPE_NAMES[m] ?? m)}
            </Link>
          ))}
        </div>

        <section className="mb-12">
          <h2 className="text-xl font-bold text-foreground mb-4">Classic maps</h2>
          {official.length === 0 ? (
            <p className="text-text-muted">No classic maps published yet.</p>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {official.map((m) => (
                <MapCard key={m.code} map={m} />
              ))}
            </div>
          )}
        </section>

        <section>
          <h2 className="text-xl font-bold text-foreground mb-4">Community maps</h2>
          {community.length === 0 ? (
            <div className="flex items-center gap-3 text-text-muted">
              <MapIcon className="w-5 h-5" />
              <p>No community maps yet. Convert one and publish it from the tag editor.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {community.map((m) => (
                <MapCard key={m.code} map={m} />
              ))}
            </div>
          )}
        </section>
      </main>

      <Footer />
    </>
  );
}
