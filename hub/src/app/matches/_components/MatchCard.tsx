import Link from "next/link";
import { Clock, Swords, Users } from "lucide-react";

import { GAME_TYPE_NAMES } from "@/kit/types";
import type { MatchPodiumSeat, MatchSummary } from "@/lib/api/matches";
import { MapCover, PlaceBadge, PlayerAvatar, Pill, TEAM_BG, TEAM_TEXT, TeamDot, WinnerTag } from "../../components/ui";
import { LocalTime } from "./LocalTime";
import { duration, kd, winnerText } from "./format";

const OUTCOME_PILL = {
  win: { tone: "green", label: "Victory" },
  loss: { tone: "red", label: "Defeat" },
  draw: { tone: "neutral", label: "Draw" },
} as const;

/**
 * A match as a card: the map's picture, who won, and the podium. With
 * `seat`, the card leads with that player's own result instead.
 *
 * The whole card is one link laid over it, so a grid
 * of twenty-five is twenty-five tab stops, not a hundred.
 */
export function MatchCard({ match: m, priority = false }: { match: MatchSummary; priority?: boolean }) {
  const mapName = m.map_title ?? m.map_code;
  const mode = GAME_TYPE_NAMES[m.game_type] ?? m.game_type;
  return (
    <article className="group card-lift relative flex w-full flex-col overflow-hidden rounded-2xl border border-border bg-surface hover:border-gold/40">
      <div className="relative">
        <MapCover src={m.map_cover_url} code={m.map_code} priority={priority} />
        <div aria-hidden className="absolute inset-0 bg-gradient-to-t from-surface via-surface/30 to-transparent" />
        <div className="absolute left-3 top-3 flex flex-wrap gap-1.5">
          <Pill tone="solid">{mode}</Pill>
        </div>
        <div className="absolute right-3 top-3">
          <Pill tone="solid">
            <Clock aria-hidden className="h-3 w-3" />
            <span className="sr-only">Length</span>
            {duration(m.duration_ms)}
          </Pill>
        </div>
        <div className="absolute inset-x-4 bottom-3">
          <h3 className="truncate text-xl font-black text-foreground drop-shadow">{mapName}</h3>
          <p className="text-xs text-text-muted">
            <LocalTime sql={m.ended_at} />
          </p>
        </div>
      </div>

      <div className="flex flex-1 flex-col gap-4 p-4 pt-3">
        {m.player ? <SeatResult match={m} /> : <Result match={m} />}
        <Podium match={m} />
        <p className="mt-auto flex items-center gap-3 border-t border-border pt-3 text-xs text-text-muted">
          <span className="inline-flex items-center gap-1">
            <Users aria-hidden className="h-3.5 w-3.5" />
            {m.player_count} player{m.player_count === 1 ? "" : "s"}
          </span>
          <span className="truncate">Hosted by {m.host}</span>
        </p>
      </div>
      {/* Last and on top, so every part of the card opens the match. The
          inset ring keeps the focus outline inside the card's clipped edge. */}
      <Link
        href={`/matches/${m.id}`}
        aria-label={`${mode} on ${mapName}, ${winnerText(m)}`}
        className="absolute inset-0 z-[1] rounded-2xl focus-visible:-outline-offset-2"
      />
    </article>
  );
}

/** The headline: the winning player large, the team score, or why there is no winner. */
function Result({ match: m }: { match: MatchSummary }) {
  if (m.team_game && m.red_score !== null && m.blue_score !== null) {
    return <TeamScore match={m} />;
  }
  const winner = m.end_reason !== "abandoned" ? m.podium.find((p) => p.outcome === "win") : undefined;
  if (winner) {
    return (
      <div className="flex items-center gap-3 rounded-xl border border-gold/30 bg-gradient-to-r from-gold/15 to-transparent p-3">
        <PlayerAvatar name={winner.name} user={winner.user} size="lg" ring={1} />
        <div className="min-w-0 flex-1">
          <WinnerTag />
          <p className="mt-1 truncate text-lg font-bold text-foreground">{winner.name}</p>
        </div>
        <div className="text-right">
          <p className="text-2xl font-black tabular-nums text-gold">{winner.score}</p>
          <p className="text-[11px] uppercase tracking-wide text-text-muted">score</p>
        </div>
      </div>
    );
  }
  return (
    <div className="flex items-center gap-2 rounded-xl border border-border bg-surface-raised/60 p-3 text-sm font-semibold text-text-muted">
      <Swords aria-hidden className="h-4 w-4" />
      {winnerText(m)}
    </div>
  );
}

/** Red against blue, as numbers and as a bar of each side's share. */
function TeamScore({ match: m }: { match: MatchSummary }) {
  const red = m.red_score ?? 0;
  const blue = m.blue_score ?? 0;
  const total = red + blue;
  const redShare = total === 0 ? 50 : Math.round((red / total) * 100);
  const won = m.end_reason === "abandoned" ? null : m.winner;
  const side = (team: "red" | "blue", score: number) => (
    <div className={`flex flex-col ${team === "blue" ? "items-end text-right" : ""}`}>
      <span className={`text-xs font-bold uppercase tracking-wide ${TEAM_TEXT[team]}`}>{team} team</span>
      <span className={`text-3xl font-black tabular-nums ${won === team ? "text-foreground" : "text-text-muted"}`}>{score}</span>
      {won === team && <WinnerTag className="mt-1" />}
    </div>
  );
  return (
    <div className="rounded-xl border border-border bg-surface-raised/60 p-3">
      <div className="flex items-start justify-between gap-3">
        {side("red", red)}
        <span aria-hidden className="pt-6 text-sm font-bold text-text-dim">vs</span>
        {side("blue", blue)}
      </div>
      <div aria-hidden className="mt-3 flex h-1.5 overflow-hidden rounded-full bg-surface-hover">
        <span className={TEAM_BG.red} style={{ width: `${redShare}%` }} />
        <span className={`${TEAM_BG.blue} flex-1`} />
      </div>
      {(won === null || won === "draw") && (
        <p className="mt-2 text-center text-xs font-semibold uppercase tracking-wide text-text-muted">{winnerText(m)}</p>
      )}
    </div>
  );
}

/** A player's own line, on their history: how they did in this match. */
function SeatResult({ match: m }: { match: MatchSummary }) {
  const p = m.player!;
  const outcome = p.outcome ? OUTCOME_PILL[p.outcome] : null;
  return (
    <div className="flex items-center gap-3 rounded-xl border border-border bg-surface-raised/60 p-3">
      <PlaceBadge place={p.place} size="md" />
      <div className="min-w-0 flex-1">
        {outcome ? <Pill tone={outcome.tone}>{outcome.label}</Pill> : <Pill>Abandoned</Pill>}
        <p className="mt-1 text-xs text-text-muted">
          {p.place} of {m.player_count} · {p.kills} kills · {p.deaths} deaths · {kd(p.kills, p.deaths)} K/D
        </p>
      </div>
      <div className="text-right">
        <p className="text-2xl font-black tabular-nums text-foreground">{p.score}</p>
        <p className="text-[11px] uppercase tracking-wide text-text-muted">score</p>
      </div>
    </div>
  );
}

/** The top three, gold, silver and bronze. The free-for-all winner is already the headline. */
function Podium({ match: m }: { match: MatchSummary }) {
  const headline = !m.team_game && !m.player && m.end_reason !== "abandoned";
  const seats = m.podium.filter((p) => !(headline && p.outcome === "win"));
  if (seats.length === 0) return null;
  // Nobody scored (a match quit at the start): a row of "1st" medals would
  // say the opposite, so list who played without places.
  const ranked = seats.some((p) => p.score !== 0);
  return (
    <ol aria-label={ranked ? "Top players" : "Players"} className="space-y-1.5">
      {seats.map((p) => (
        <PodiumRow key={p.index} seat={p} ranked={ranked} />
      ))}
    </ol>
  );
}

function PodiumRow({ seat: p, ranked }: { seat: MatchPodiumSeat; ranked: boolean }) {
  return (
    <li className="flex items-center gap-2.5 text-sm">
      {ranked && <PlaceBadge place={p.place} />}
      <PlayerAvatar name={p.name} user={p.user} size="sm" />
      <span className="min-w-0 flex-1 truncate text-foreground">{p.name}</span>
      <TeamDot team={p.team} />
      <span className="tabular-nums font-semibold text-text-muted">{p.score}</span>
    </li>
  );
}

/** The cards, one to three across. Only the first image is fetched eagerly: on a phone it is the only one on screen, and more would compete with it. */
export function MatchGrid({ matches }: { matches: MatchSummary[] }) {
  return (
    <ul className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
      {matches.map((m, i) => (
        <li key={m.id} className="flex">
          <MatchCard match={m} priority={i === 0} />
        </li>
      ))}
    </ul>
  );
}
