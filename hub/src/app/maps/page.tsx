import Link from "next/link";
import { Map as MapIcon, Rocket, Search, Upload, X } from "lucide-react";
import { getCloudflareContext } from "@opennextjs/cloudflare";

import { LAUNCHER_LINK_TITLE } from "../components/JoinButton";
import {
  ButtonLink,
  EmptyState,
  FilterBar,
  FilterChips,
  MapCover,
  PageHeader,
  PageShell,
  Pill,
  SectionHeading,
  SelectNav,
} from "../components/ui";
import { listMaps } from "@/lib/api/maps";
import { GAME_TYPE_NAMES, MAP_GAME_NAMES, MAP_SIZES } from "@/kit/types";
import type { MapGame, MapListing, MapSize, MapSort } from "@/kit/types";
import { MAP_FILTER_MODES, modeLabel } from "@/lib/filters";
import { marketingMetadata } from "@/lib/marketing";

export const metadata = marketingMetadata(
  "Halo Campaign Evolved Multiplayer Maps | MJOLNIR Core",
  "Play the classic Halo CE and Halo 2 multiplayer maps in Campaign Evolved with MJOLNIR. Browse Blood Gulch, Lockout, and community maps with supported game modes.",
  "/maps",
);

const SHOWS = [
  { key: "all", label: "All maps" },
  { key: "classic", label: "Classic" },
  { key: "community", label: "Community" },
] as const;
const GAMES = ["any", "halo1", "halo2"] as const;
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
  if (map.game) facts.push(MAP_GAME_NAMES[map.game]);
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

function MapCard({ map, priority }: { map: MapListing; priority: boolean }) {
  const facts = mapFacts(map);
  // The title's link is stretched over the card; the launcher link sits
  // above it, since an anchor cannot nest another.
  return (
    <article className="group card-lift relative flex w-full flex-col overflow-hidden rounded-2xl border border-border bg-surface hover:border-gold/40">
      <div className="relative">
        <MapCover src={map.cover_url} code={map.code} priority={priority} />
        <div className="absolute left-3 top-3">
          <Pill tone="solid">{map.official ? "Classic" : "Community"}</Pill>
        </div>
        <span className="absolute right-3 top-3 rounded-md bg-background/80 px-1.5 py-0.5 font-mono text-[11px] font-bold text-text-muted backdrop-blur-sm">
          {map.code}
        </span>
      </div>
      <div className="flex flex-1 flex-col px-4 pt-4">
        <h3 className="truncate text-lg font-bold text-foreground">
          <Link
            href={`/mods/${map.slug}`}
            className="after:absolute after:inset-0 after:content-[''] focus-visible:outline-none group-has-[:focus-visible]:underline"
          >
            {map.title}
          </Link>
        </h3>
        {facts.length > 0 && <p className="mt-0.5 text-xs text-text-muted">{facts.join(" · ")}</p>}
        <p className="mt-2 line-clamp-2 min-h-[2.5rem] text-sm text-text-muted">{map.summary ?? "No summary."}</p>
        <ul aria-label="Game types" className="mt-3 flex flex-wrap gap-1.5">
          {map.modes.map((m) => (
            <li key={m}>
              <Pill tone="gold" className="normal-case tracking-normal">
                {GAME_TYPE_NAMES[m] ?? m}
              </Pill>
            </li>
          ))}
        </ul>
      </div>
      <div className="mt-3 flex items-center justify-between gap-3 border-t border-border px-4 py-3 text-xs text-text-muted">
        <div className="flex min-w-0 items-center gap-3">
          {map.release ? <span>v{map.release.version}</span> : <span>No release yet</span>}
          {map.release?.file_size ? <span>{sizeOf(map.release.file_size)}</span> : null}
          {!map.official && <span className="truncate">by {map.owner}</span>}
        </div>
        {map.release && (
          <a
            href={`mjolnir://map/${map.code}`}
            title={`${LAUNCHER_LINK_TITLE} on this map's page.`}
            className="relative z-[1] inline-flex min-h-8 shrink-0 items-center gap-1 rounded-md px-2 font-semibold text-gold hover:bg-gold/10"
          >
            <Rocket aria-hidden className="h-3.5 w-3.5" />
            Open in launcher
          </a>
        )}
      </div>
    </article>
  );
}

function MapGrid({ maps, eager = false }: { maps: MapListing[]; eager?: boolean }) {
  return (
    <ul className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
      {maps.map((m, i) => (
        <li key={m.code} className="flex">
          <MapCard map={m} priority={eager && i === 0} />
        </li>
      ))}
    </ul>
  );
}

export default async function MapsPage({
  searchParams,
}: {
  searchParams: Promise<{
    q?: string;
    mode?: string;
    show?: string;
    game?: string;
    size?: string;
    vehicles?: string;
    sort?: string;
  }>;
}) {
  const params = await searchParams;
  const q = params.q?.trim().slice(0, 80) || undefined;
  const mode = MAP_FILTER_MODES.find((m) => m === params.mode) ?? "all";
  const show = SHOWS.find((s) => s.key === params.show)?.key ?? "all";
  const game = GAMES.find((g) => g === params.game) ?? "any";
  const size = SIZES.find((s) => s === params.size) ?? "any";
  const vehicles = VEHICLES.find((v) => v.key === params.vehicles)?.key ?? "any";
  const sort = SORTS.find((s) => s.key === params.sort)?.key ?? "default";

  const { env } = getCloudflareContext();
  const maps = await listMaps(env.DB as never, {
    q,
    mode: mode === "all" ? undefined : mode,
    official: show === "all" ? undefined : show === "classic",
    game: game === "any" ? undefined : (game as MapGame),
    size: size === "any" ? undefined : (size as MapSize),
    vehicles: vehicles === "any" ? undefined : vehicles === "1",
    sort: sort === "default" ? undefined : (sort as MapSort),
  });
  // The classic/community split reads well as the catalog's front page; a
  // search, a sort or a pick of one side is a single list of results.
  const sectioned = !q && sort === "default" && show === "all";
  const filtered =
    !!q || mode !== "all" || show !== "all" || game !== "any" || size !== "any" || vehicles !== "any";
  const official = maps.filter((m) => m.official);
  const community = maps.filter((m) => !m.official);

  const current = { q: q ?? "", mode, show, game, size, vehicles, sort };
  const set = (v: string) => v && v !== "all" && v !== "any" && v !== "default";
  const qs = (over: Partial<Record<keyof typeof current, string>>) => {
    const merged = { ...current, ...over };
    const u = new URLSearchParams();
    for (const [k, v] of Object.entries(merged)) if (set(v)) u.set(k, v);
    const s = u.toString();
    return s ? `/maps?${s}` : "/maps";
  };
  /** Every filter but one, for a form that sets that one. */
  const others = (except: keyof typeof current) =>
    Object.fromEntries(Object.entries(current).filter(([k, v]) => k !== except && set(v)));

  return (
    <PageShell>
      <PageHeader
        eyebrow="Classic battlegrounds. Community creations."
        title="Multiplayer maps"
        description={
          <>
            The original Halo: Combat Evolved and Halo 2 multiplayer maps, rebuilt for Campaign Evolved, plus a home
            for custom maps from the community. The launcher installs each map and everything it needs.{" "}
            <Link href="/multiplayer#setup" className="font-semibold text-gold hover:underline">
              New here? Set up multiplayer →
            </Link>
          </>
        }
        actions={
          <ButtonLink href="/docs/notes/map-distribution" variant="secondary">
            <Upload aria-hidden className="h-4 w-4" />
            Make a map
          </ButtonLink>
        }
      />

      <FilterBar>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          {/* Search keeps every other filter; the chips each change one. */}
          <form action="/maps" method="get" role="search" className="relative sm:w-72">
            <label htmlFor="map-search" className="sr-only">
              Search maps
            </label>
            <Search
              aria-hidden
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted"
            />
            <input
              id="map-search"
              type="search"
              name="q"
              defaultValue={q ?? ""}
              maxLength={80}
              placeholder="Search maps…"
              className="min-h-10 w-full rounded-lg border border-border bg-surface-raised pl-9 pr-3 text-sm text-foreground placeholder:text-text-muted hover:border-border-bright focus:border-gold/60"
            />
            {Object.entries(others("q")).map(([k, v]) => (
              <input key={k} type="hidden" name={k} value={v} />
            ))}
          </form>
          <SelectNav
            label="Sort"
            name="sort"
            value={sort}
            action="/maps"
            hidden={others("sort")}
            options={SORTS.map((s) => ({ value: s.key, label: s.label, href: qs({ sort: s.key }) }))}
          />
        </div>
        <FilterChips
          label="Game type"
          options={MAP_FILTER_MODES.map((m) => ({ label: modeLabel(m), href: qs({ mode: m }), active: m === mode }))}
        />
        <div className="flex flex-col gap-3 border-t border-border pt-3 xl:flex-row xl:flex-wrap xl:items-center xl:gap-x-6">
          <FilterChips
            label="Origin"
            options={SHOWS.map((x) => ({ label: x.label, href: qs({ show: x.key }), active: show === x.key }))}
          />
          <FilterChips
            label="Game"
            options={GAMES.map((g) => ({
              label: g === "any" ? "Any game" : MAP_GAME_NAMES[g],
              href: qs({ game: g }),
              active: game === g,
            }))}
          />
          <FilterChips
            label="Size"
            options={SIZES.map((x) => ({
              label: x === "any" ? "Any size" : MAP_SIZES[x],
              href: qs({ size: x }),
              active: size === x,
            }))}
          />
          <FilterChips
            label="Vehicles"
            options={VEHICLES.map((v) => ({ label: v.label, href: qs({ vehicles: v.key }), active: vehicles === v.key }))}
          />
        </div>
      </FilterBar>

      <div className="mb-6 flex min-h-9 items-center justify-between gap-3 text-sm text-text-muted">
        <p aria-live="polite">
          {maps.length} map{maps.length === 1 ? "" : "s"}
          {q ? ` matching “${q}”` : ""}
        </p>
        {filtered && (
          <Link href="/maps" className="inline-flex min-h-9 items-center gap-1 rounded-lg px-2 hover:text-foreground">
            <X aria-hidden className="h-4 w-4" />
            Clear filters
          </Link>
        )}
      </div>

      {!sectioned ? (
        maps.length === 0 ? (
          <EmptyState
            icon={MapIcon}
            title="No maps match"
            action={
              <ButtonLink href="/maps" variant="secondary">
                Clear filters
              </ButtonLink>
            }
          >
            Try fewer filters or a different search.
          </EmptyState>
        ) : (
          <MapGrid maps={maps} eager />
        )
      ) : (
        <>
          <section aria-labelledby="classic-maps" className="mb-14">
            <SectionHeading id="classic-maps" aside={<span className="text-text-muted">{official.length}</span>}>
              Classic maps
            </SectionHeading>
            {official.length === 0 ? (
              <p className="text-text-muted">{filtered ? "No classic maps match." : "No classic maps published yet."}</p>
            ) : (
              <MapGrid maps={official} eager />
            )}
          </section>

          <section aria-labelledby="community-maps">
            <SectionHeading id="community-maps" aside={<span className="text-text-muted">{community.length}</span>}>
              Community maps
            </SectionHeading>
            {community.length === 0 ? (
              <EmptyState
                icon={MapIcon}
                title={filtered ? "No community maps match" : "No community maps yet"}
                action={
                  filtered ? undefined : (
                    <ButtonLink href="/docs/notes/map-distribution" variant="secondary">
                      Publish a map
                    </ButtonLink>
                  )
                }
              >
                {filtered
                  ? "Try fewer filters."
                  : "Convert one, pack it with mjolnir map pack, and upload it from your mod's page."}
              </EmptyState>
            ) : (
              <MapGrid maps={community} />
            )}
          </section>
        </>
      )}
    </PageShell>
  );
}
