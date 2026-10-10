import Link from "next/link";
import { Map as MapIcon, Rocket, Search, Upload } from "lucide-react";
import { getCloudflareContext } from "@opennextjs/cloudflare";

import { Navbar } from "../components/Navbar";
import { Footer } from "../components/Footer";
import { LAUNCHER_LINK_TITLE } from "../components/JoinButton";
import { listMaps } from "@/lib/api/maps";
import { GAME_TYPE_NAMES, MAP_SIZES } from "@/kit/types";
import type { MapListing, MapSize, MapSort } from "@/kit/types";
import { marketingMetadata } from "@/lib/marketing";

export const metadata = marketingMetadata(
  "Halo Campaign Evolved Multiplayer Maps | MJOLNIR Core",
  "Play all 19 original Halo CE multiplayer maps in Campaign Evolved with MJOLNIR. Browse Blood Gulch, Sidewinder, and community maps with supported game modes.",
  "/maps",
);

const MODES = ["all", "slayer", "ctf", "team_slayer", "koth", "oddball"];
const SHOWS = [
  { key: "all", label: "All maps" },
  { key: "classic", label: "Classic" },
  { key: "community", label: "Community" },
] as const;
const SIZES = ["any", "small", "medium", "large"] as const;
const VEHICLES = [
  { key: "any", label: "Vehicles or not" },
  { key: "1", label: "Vehicles" },
  { key: "0", label: "No vehicles" },
] as const;
const SORTS = [
  { key: "default", label: "Classics first" },
  { key: "newest", label: "Newest" },
  { key: "downloads", label: "Most downloaded" },
  { key: "rating", label: "Top rated" },
  { key: "title", label: "A–Z" },
] as const;

function sizeOf(bytes: number | null): string {
  if (!bytes) return "";
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** "Large · 4–16 players · vehicles", from whatever the map declared. */
function mapFacts(map: MapListing): string[] {
  const facts: string[] = [];
  if (map.size) facts.push(MAP_SIZES[map.size]);
  if (map.players_min !== null && map.players_max !== null) {
    facts.push(
      map.players_min === map.players_max
        ? `${map.players_min} players`
        : `${map.players_min}–${map.players_max} players`,
    );
  }
  if (map.vehicles !== null) facts.push(map.vehicles ? "vehicles" : "no vehicles");
  return facts;
}

function MapCard({ map }: { map: MapListing }) {
  const facts = mapFacts(map);
  // The card is a link to the map's page, and the launcher link sits
  // beside it rather than inside: an anchor cannot nest another.
  return (
    <div className="group flex flex-col bg-surface border border-border rounded-xl overflow-hidden hover:border-gold/40 transition-colors">
      <Link href={`/mods/${map.slug}`} className="block flex-1">
        {map.cover_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={map.cover_url}
            alt={`${map.title} in Halo Campaign Evolved`}
            loading="lazy"
            className="w-full aspect-video object-cover bg-surface-raised"
          />
        ) : (
          <div className="w-full aspect-video bg-surface-raised" />
        )}
        <div className="px-4 pt-4">
          <div className="flex items-center justify-between gap-2">
            <span className="font-semibold text-foreground truncate">{map.title}</span>
            <span className="text-[11px] font-mono text-text-dim">{map.code}</span>
          </div>
          {facts.length > 0 && <p className="text-xs text-text-muted mt-0.5">{facts.join(" · ")}</p>}
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
        </div>
      </Link>
      <div className="flex items-center justify-between gap-3 px-4 pb-4 pt-3 text-xs text-text-dim">
        <div className="flex items-center gap-3 min-w-0">
          {map.release ? <span>v{map.release.version}</span> : <span>no release yet</span>}
          {map.release?.file_size ? <span>{sizeOf(map.release.file_size)}</span> : null}
          {!map.official && <span className="truncate">by {map.owner}</span>}
        </div>
        {map.release && (
          <a
            href={`mjolnir://map/${map.code}`}
            title={`${LAUNCHER_LINK_TITLE} and installs this map.`}
            className="shrink-0 inline-flex items-center gap-1 font-semibold text-gold hover:underline"
          >
            <Rocket className="w-3 h-3" />
            Install in launcher
          </a>
        )}
      </div>
    </div>
  );
}

function MapGrid({ maps }: { maps: MapListing[] }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      {maps.map((m) => (
        <MapCard key={m.code} map={m} />
      ))}
    </div>
  );
}

export default async function MapsPage({
  searchParams,
}: {
  searchParams: Promise<{
    q?: string;
    mode?: string;
    show?: string;
    size?: string;
    vehicles?: string;
    sort?: string;
  }>;
}) {
  const params = await searchParams;
  const q = params.q?.trim().slice(0, 80) || undefined;
  const mode = MODES.find((m) => m === params.mode) ?? "all";
  const show = SHOWS.find((s) => s.key === params.show)?.key ?? "all";
  const size = SIZES.find((s) => s === params.size) ?? "any";
  const vehicles = VEHICLES.find((v) => v.key === params.vehicles)?.key ?? "any";
  const sort = SORTS.find((s) => s.key === params.sort)?.key ?? "default";

  const { env } = getCloudflareContext();
  const maps = await listMaps(env.DB as never, {
    q,
    mode: mode === "all" ? undefined : mode,
    official: show === "all" ? undefined : show === "classic",
    size: size === "any" ? undefined : (size as MapSize),
    vehicles: vehicles === "any" ? undefined : vehicles === "1",
    sort: sort === "default" ? undefined : (sort as MapSort),
  });
  // The classic/community split reads well as the catalog's front page; a
  // search, a sort or a pick of one side is a single list of results.
  const sectioned = !q && sort === "default" && show === "all";
  const filtered = !!q || mode !== "all" || show !== "all" || size !== "any" || vehicles !== "any";
  const official = maps.filter((m) => m.official);
  const community = maps.filter((m) => !m.official);

  const current = { q: q ?? "", mode, show, size, vehicles, sort };
  const qs = (over: Partial<Record<keyof typeof current, string>>) => {
    const merged = { ...current, ...over };
    const u = new URLSearchParams();
    for (const [k, v] of Object.entries(merged)) {
      if (v && v !== "all" && v !== "any" && v !== "default") u.set(k, v);
    }
    const s = u.toString();
    return s ? `/maps?${s}` : "/maps";
  };
  const chip = (active: boolean) =>
    `px-3 py-1.5 rounded-full border transition-colors ${
      active ? "border-gold/60 text-gold bg-gold/10" : "border-border text-text-muted hover:text-foreground"
    }`;

  return (
    <>
      <Navbar />

      <main className="marketing pt-40 md:pt-44 pb-16 px-6 max-w-6xl mx-auto">
        <div className="mb-10 flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="marketing-eyebrow mb-3">Classic battlegrounds. Community creations.</p>
            <h1 className="text-4xl font-black text-foreground mb-3">Campaign Evolved multiplayer maps</h1>
            <p className="text-text-muted text-lg max-w-2xl">
              All 19 original Halo: Combat Evolved multiplayer maps, rebuilt for Campaign
              Evolved, plus a home for custom maps from the community. The launcher installs
              each map and everything it needs.
            </p>
            <Link href="/multiplayer#setup" className="mt-4 inline-block text-sm font-semibold text-gold hover:underline">New here? Set up Campaign Evolved multiplayer →</Link>
          </div>
          <Link
            href="/docs/notes/map-distribution"
            className="flex items-center gap-2 px-4 py-2 text-sm font-semibold rounded-lg border border-border text-foreground hover:border-gold/40 transition-colors"
          >
            <Upload className="w-4 h-4" />
            Make a map
          </Link>
        </div>

        {/* Search keeps every other filter; the chips each change one. */}
        <form action="/maps" method="get" className="mb-4 flex flex-wrap items-center gap-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-dim" />
            <input
              type="search"
              name="q"
              defaultValue={q ?? ""}
              maxLength={80}
              placeholder="Search maps…"
              className="pl-9 pr-3 py-2 text-sm rounded-lg bg-background border border-border text-foreground placeholder:text-text-dim focus:border-gold/60 focus:outline-none w-64"
            />
          </div>
          {mode !== "all" && <input type="hidden" name="mode" value={mode} />}
          {show !== "all" && <input type="hidden" name="show" value={show} />}
          {size !== "any" && <input type="hidden" name="size" value={size} />}
          {vehicles !== "any" && <input type="hidden" name="vehicles" value={vehicles} />}
          {sort !== "default" && <input type="hidden" name="sort" value={sort} />}
          <div className="flex flex-wrap items-center gap-1 text-xs">
            {SORTS.map((s) => (
              <Link key={s.key} href={qs({ sort: s.key })} className={chip(sort === s.key)}>
                {s.label}
              </Link>
            ))}
          </div>
        </form>

        <div className="mb-3 flex flex-wrap items-center gap-1 text-xs">
          {SHOWS.map((s) => (
            <Link key={s.key} href={qs({ show: s.key })} className={chip(show === s.key)}>
              {s.label}
            </Link>
          ))}
          <span className="mx-2 h-4 w-px bg-border" aria-hidden="true" />
          {SIZES.map((s) => (
            <Link key={s} href={qs({ size: s })} className={chip(size === s)}>
              {s === "any" ? "Any size" : MAP_SIZES[s]}
            </Link>
          ))}
          <span className="mx-2 h-4 w-px bg-border" aria-hidden="true" />
          {VEHICLES.map((v) => (
            <Link key={v.key} href={qs({ vehicles: v.key })} className={chip(vehicles === v.key)}>
              {v.label}
            </Link>
          ))}
        </div>
        <div className="mb-8 flex flex-wrap items-center gap-1 text-xs">
          {MODES.map((m) => (
            <Link key={m} href={qs({ mode: m })} className={chip(m === mode)}>
              {m === "all" ? "All game types" : (GAME_TYPE_NAMES[m] ?? m)}
            </Link>
          ))}
          {filtered && (
            <Link href="/maps" className="ml-2 px-3 py-1.5 text-text-dim hover:text-foreground">
              Clear filters
            </Link>
          )}
        </div>

        {!sectioned ? (
          maps.length === 0 ? (
            <div className="flex items-center gap-3 text-text-muted">
              <MapIcon className="w-5 h-5" />
              <p>No maps match. Try fewer filters.</p>
            </div>
          ) : (
            <MapGrid maps={maps} />
          )
        ) : (
          <>
            <section className="mb-12">
              <h2 className="text-xl font-bold text-foreground mb-4">Classic maps</h2>
              {official.length === 0 ? (
                <p className="text-text-muted">
                  {filtered ? "No classic maps match." : "No classic maps published yet."}
                </p>
              ) : (
                <MapGrid maps={official} />
              )}
            </section>

            <section>
              <h2 className="text-xl font-bold text-foreground mb-4">Community maps</h2>
              {community.length === 0 ? (
                <div className="flex items-center gap-3 text-text-muted">
                  <MapIcon className="w-5 h-5" />
                  <p>
                    {filtered
                      ? "No community maps match."
                      : "No community maps yet. Convert one and publish it from the tag editor."}
                  </p>
                </div>
              ) : (
                <MapGrid maps={community} />
              )}
            </section>
          </>
        )}
      </main>

      <Footer />
    </>
  );
}
