import { History, Radio, Users } from "lucide-react";
import { getCloudflareContext } from "@opennextjs/cloudflare";

import { LobbyCard } from "../components/LobbyCard";
import { ButtonLink, EmptyState, FilterBar, FilterChips, PageHeader, PageShell, SelectNav, ToggleChip } from "../components/ui";
import { listLobbies } from "@/lib/api/lobby";
import { listMaps } from "@/lib/api/maps";
import { GAME_MODES, modeLabel, parseMapCode, parseMode, withQuery } from "@/lib/filters";
import { marketingMetadata } from "@/lib/marketing";

export const metadata = marketingMetadata(
  "Halo Campaign Evolved Multiplayer Games | MJOLNIR Core",
  "Find reported Campaign Evolved multiplayer lobbies on classic Halo CE maps. Get MJOLNIR, install the maps, and connect with the community.",
  "/games",
);

// Live data: never cached.
export const dynamic = "force-dynamic";

function num(v: unknown): number | null {
  return v === undefined || v === null || v === "" ? null : Number(v);
}

export default async function GamesPage({
  searchParams,
}: {
  searchParams: Promise<{ map?: string; mode?: string; open?: string }>;
}) {
  const params = await searchParams;
  const mode = parseMode(params.mode);
  const map = parseMapCode(params.map);
  const open = params.open === "1";

  const { env, cf } = getCloudflareContext();
  const me = {
    latitude: num((cf as Record<string, unknown> | undefined)?.latitude),
    longitude: num((cf as Record<string, unknown> | undefined)?.longitude),
  };
  const [lobbies, maps] = await Promise.all([
    listLobbies(
      env.DB as never,
      { map, game_type: mode === "all" ? undefined : mode, has_space: open },
      me,
    ),
    listMaps(env.DB as never),
  ]);
  const covers = new Map(maps.map((m) => [m.code, m.cover_url]));

  const href = (over: Record<string, string | undefined>) =>
    withQuery("/games", { mode, map, open: open ? "1" : undefined, ...over });
  const players = lobbies.reduce((n, l) => n + l.players, 0);

  return (
    <PageShell>
      <PageHeader
        eyebrow={
          <span className="inline-flex items-center gap-2">
            <span aria-hidden className="h-2 w-2 animate-pulse rounded-full bg-accent-green motion-reduce:animate-none" />
            Live now
          </span>
        }
        title="Multiplayer games"
        description={
          <>
            Public games on the classic maps, right now. Join from the game (MULTIPLAYER, then FIND GAMES), or press
            Join here to open it in the launcher (0.13.0 or newer). Ping is an estimate from where you and the host
            are.
          </>
        }
        actions={
          <>
            <ButtonLink href="/multiplayer">Get multiplayer</ButtonLink>
            <ButtonLink href="/matches" variant="secondary">
              <History aria-hidden className="h-4 w-4" />
              Match history
            </ButtonLink>
          </>
        }
      />

      <FilterBar>
        <FilterChips
          label="Game type"
          options={GAME_MODES.map((m) => ({ label: modeLabel(m), href: href({ mode: m }), active: m === mode }))}
        />
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border pt-3">
          <SelectNav
            label="Map"
            name="map"
            value={map ?? ""}
            action="/games"
            hidden={{ mode: mode === "all" ? undefined : mode, open: open ? "1" : undefined }}
            options={[
              { value: "", label: "All maps", href: href({ map: undefined }) },
              ...maps.map((m) => ({ value: m.code, label: m.title, href: href({ map: m.code }) })),
            ]}
          />
          <ToggleChip href={href({ open: open ? undefined : "1" })} active={open}>
            <Users aria-hidden className="h-4 w-4" />
            Has room
          </ToggleChip>
        </div>
      </FilterBar>

      {lobbies.length > 0 && (
        <p className="mb-4 text-sm text-text-muted" aria-live="polite">
          {lobbies.length} game{lobbies.length === 1 ? "" : "s"} · {players} player{players === 1 ? "" : "s"} online
        </p>
      )}

      <h2 className="sr-only">Games</h2>
      {lobbies.length === 0 ? (
        <EmptyState
          icon={Radio}
          title="No games right now"
          action={<ButtonLink href="/multiplayer">How to host a game</ButtonLink>}
        >
          Host one from the game, set it to PUBLIC GAME in the lobby, and it shows up here.
        </EmptyState>
      ) : (
        <ul className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {lobbies.map((l) => (
            <li key={l.id} className="flex">
              <LobbyCard lobby={l} coverUrl={covers.get(l.map_code) ?? null} />
            </li>
          ))}
        </ul>
      )}
    </PageShell>
  );
}
