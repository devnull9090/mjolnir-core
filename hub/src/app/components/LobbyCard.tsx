import { Signal, Users } from "lucide-react";

import { GAME_TYPE_NAMES } from "@/kit/types";
import type { Lobby } from "@/lib/api/lobby";
import { JoinButton } from "./JoinButton";
import { MapCover, Pill } from "./ui";

/**
 * A game you can join right now: its map, its mode, how full it is, and
 * the Join hand-off to the launcher. Used by the live games page and the
 * "Live now" strip above the match history.
 */
export function LobbyCard({ lobby: l, coverUrl, compact = false }: { lobby: Lobby; coverUrl: string | null; compact?: boolean }) {
  const full = l.state === "full" || l.players >= l.max_players;
  const fill = Math.min(100, Math.round((l.players / Math.max(1, l.max_players)) * 100));
  return (
    <article className="group flex w-full overflow-hidden rounded-2xl border border-border bg-surface transition-colors hover:border-gold/40">
      <MapCover
        src={coverUrl}
        code={l.map_code}
        className={`${compact ? "w-28" : "w-32 sm:w-44"} shrink-0 !aspect-auto`}
      />
      <div className="flex min-w-0 flex-1 flex-col gap-2 p-3 sm:p-4">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <h3 className="truncate font-bold text-foreground">{l.name}</h3>
            <p className="truncate text-sm text-text-muted">
              {l.map_title ?? l.map_code} · {GAME_TYPE_NAMES[l.game_type] ?? l.game_type}
            </p>
          </div>
          {l.state === "in_game" ? (
            <Pill tone="gold">In game</Pill>
          ) : (
            <Pill tone="green">
              <span aria-hidden className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent-green motion-reduce:animate-none" />
              Lobby
            </Pill>
          )}
        </div>
        <div className="mt-auto flex items-end justify-between gap-3">
          <div className="min-w-0 flex-1 text-xs text-text-muted">
            <p className="flex items-center gap-3">
              <span className="inline-flex items-center gap-1 font-semibold text-foreground">
                <Users aria-hidden className="h-3.5 w-3.5" />
                {l.players}/{l.max_players}
                <span className="sr-only">players</span>
              </span>
              <span className="inline-flex items-center gap-1 whitespace-nowrap" title="Estimated ping">
                <Signal aria-hidden className="h-3.5 w-3.5" />
                <span className="sr-only">Ping </span>
                {l.ping_ms === null ? "?" : `~${l.ping_ms} ms`}
              </span>
            </p>
            <div aria-hidden className="mt-1.5 h-1 w-full max-w-40 overflow-hidden rounded-full bg-surface-hover">
              <div className={`h-full rounded-full ${full ? "bg-text-dim" : "bg-gold"}`} style={{ width: `${fill}%` }} />
            </div>
            {!compact && <p className="mt-1.5 truncate">Hosted by {l.host}</p>}
          </div>
          <JoinButton lobbyId={l.id} full={full} />
        </div>
      </div>
    </article>
  );
}
