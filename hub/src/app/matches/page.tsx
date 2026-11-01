import Link from "next/link";
import { Radio, Search, Swords } from "lucide-react";
import { getCloudflareContext } from "@opennextjs/cloudflare";

import { LobbyCard } from "../components/LobbyCard";
import {
  ButtonLink,
  EmptyState,
  FilterBar,
  FilterChips,
  PageHeader,
  PageShell,
  Pager,
  SectionHeading,
  SelectNav,
  ViewToggle,
} from "../components/ui";
import { listLobbies } from "@/lib/api/lobby";
import { listMatches } from "@/lib/api/matches";
import { listMaps } from "@/lib/api/maps";
import { GAME_MODES, modeLabel, parseMapCode, parseMode, withQuery } from "@/lib/filters";
import { marketingMetadata } from "@/lib/marketing";
import { MatchGrid } from "./_components/MatchCard";
import { MatchTable } from "./_components/MatchTable";

export const metadata = marketingMetadata(
  "Halo Campaign Evolved Match History | MJOLNIR Core",
  "Every public Campaign Evolved multiplayer match on the classic Halo CE maps: who won, the scoreboard, and every kill.",
  "/matches",
);

// Live data: never cached.
export const dynamic = "force-dynamic";

/** How many live games the strip above the history shows. */
const LIVE_SHOWN = 3;

function num(v: unknown): number | null {
  return v === undefined || v === null || v === "" ? null : Number(v);
}

export default async function MatchesPage({
  searchParams,
}: {
  searchParams: Promise<{ map?: string; mode?: string; before?: string; view?: string }>;
}) {
  const params = await searchParams;
  const mode = parseMode(params.mode);
  const map = parseMapCode(params.map);
  const before = /^[\d\- :]{10,19}$/.test(params.before ?? "") ? params.before : undefined;
  const view = params.view === "table" ? "table" : "grid";

  const { env, cf } = getCloudflareContext();
  const me = {
    latitude: num((cf as Record<string, unknown> | undefined)?.latitude),
    longitude: num((cf as Record<string, unknown> | undefined)?.longitude),
  };
  const [{ matches, next }, maps, lobbies] = await Promise.all([
    listMatches(env.DB as never, { map, game_type: mode === "all" ? undefined : mode, before }),
    listMaps(env.DB as never),
    listLobbies(env.DB as never, { has_space: true }, me),
  ]);
  const live = lobbies.slice(0, LIVE_SHOWN);
  const covers = new Map(maps.map((m) => [m.code, m.cover_url]));

  const href = (over: Record<string, string | undefined>) =>
    withQuery("/matches", { mode, map, view: view === "table" ? "table" : undefined, ...over });

  return (
    <PageShell>
      <PageHeader
        eyebrow="Service record"
        title="Match history"
        description="Every public match, reported by its host when it ends: who won, the scoreboard, and every kill with where it happened."
        actions={
          <>
            <form action="/players" role="search" className="relative w-full sm:w-auto">
              <label htmlFor="player-search" className="sr-only">
                Find a player
              </label>
              <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted" />
              <input
                id="player-search"
                name="name"
                type="search"
                placeholder="Find a player"
                maxLength={64}
                autoComplete="off"
                className="min-h-10 w-full rounded-lg border border-border bg-surface pl-9 pr-3 text-sm text-foreground placeholder:text-text-muted hover:border-border-bright focus:border-gold/60 sm:w-56"
              />
            </form>
            <ButtonLink href="/games" variant="secondary">
              <Radio aria-hidden className="h-4 w-4 text-accent-green" />
              Live games
            </ButtonLink>
          </>
        }
      />

      {/* Games with room right now, nearest first: history is what
          happened, and this is where to go next. */}
      {live.length > 0 && !before && (
        <section aria-labelledby="live-now" className="mb-10">
          <SectionHeading
            id="live-now"
            aside={
              <Link href="/games" className="font-semibold text-gold hover:underline">
                All live games →
              </Link>
            }
          >
            Live now
          </SectionHeading>
          <ul className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
            {live.map((l) => (
              <li key={l.id} className="flex">
                <LobbyCard lobby={l} coverUrl={covers.get(l.map_code) ?? null} compact />
              </li>
            ))}
          </ul>
        </section>
      )}

      <FilterBar>
        <FilterChips
          label="Game type"
          options={GAME_MODES.map((m) => ({ label: modeLabel(m), href: href({ mode: m, before: undefined }), active: m === mode }))}
        />
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-3">
          <SelectNav
            label="Map"
            name="map"
            value={map ?? ""}
            action="/matches"
            hidden={{ mode: mode === "all" ? undefined : mode, view: view === "table" ? "table" : undefined }}
            options={[
              { value: "", label: "All maps", href: href({ map: undefined }) },
              ...maps.map((m) => ({ value: m.code, label: m.title, href: href({ map: m.code }) })),
            ]}
          />
          <ViewToggle
            view={view}
            gridHref={href({ view: undefined, before })}
            tableHref={href({ view: "table", before })}
          />
        </div>
      </FilterBar>

      <h2 className="sr-only">Matches</h2>
      {matches.length === 0 ? (
        <EmptyState icon={Swords} title="No matches here yet" action={<ButtonLink href="/multiplayer">Get multiplayer</ButtonLink>}>
          {mode !== "all" || map
            ? "Nothing matches these filters. Try another map or game type."
            : "Public games report each match here when it ends."}
        </EmptyState>
      ) : view === "grid" ? (
        <MatchGrid matches={matches} />
      ) : (
        <MatchTable matches={matches} />
      )}

      <Pager newest={before ? href({ before: undefined }) : undefined} older={next ? href({ before: next }) : undefined} />
    </PageShell>
  );
}
