import Link from "next/link";
import { Swords } from "lucide-react";

import { GAME_TYPE_NAMES } from "@/kit/types";
import type { MatchSummary, PlayerTotals } from "@/lib/api/matches";
import { EmptyState, PlaceBadge, PlayerAvatar, StatGrid, StatTile, TableFrame, TeamDot, TEAM_TEXT } from "../../components/ui";
import { LocalTime } from "./LocalTime";
import { duration, kd, mapHref, playerHref, weaponName, winnerText } from "./format";

const OUTCOME_STYLE: Record<string, string> = {
  win: "text-accent-green",
  loss: "text-team-red",
  draw: "text-text-muted",
};

/**
 * A list of matches. With `seat`, each row carries that player's line
 * (place, score, kills/deaths, outcome) instead of the match's winner.
 */
export function MatchTable({ matches, seat = false }: { matches: MatchSummary[]; seat?: boolean }) {
  if (matches.length === 0) {
    return (
      <EmptyState icon={Swords} title="No matches yet">
        Public games report each match here when it ends.
      </EmptyState>
    );
  }
  return (
    <TableFrame>
      <table className="w-full text-sm">
        <thead className="bg-surface-raised text-text-muted text-xs uppercase tracking-wide">
          <tr>
            <th className="text-left px-4 py-3">Played</th>
            <th className="text-left px-4 py-3">Map</th>
            <th className="hidden md:table-cell text-left px-4 py-3">Game type</th>
            {seat ? (
              <>
                <th className="text-left px-4 py-3">Result</th>
                <th className="text-right px-4 py-3">Place</th>
                <th className="text-right px-4 py-3">Score</th>
                <th className="text-right px-4 py-3">K / D</th>
              </>
            ) : (
              <>
                <th className="text-left px-4 py-3">Winner</th>
                <th className="text-right px-4 py-3">Players</th>
              </>
            )}
            <th className="hidden sm:table-cell text-right px-4 py-3">Length</th>
          </tr>
        </thead>
        <tbody>
          {matches.map((m) => (
            <tr key={m.id} className="border-t border-border transition-colors hover:bg-surface-raised/60">
              <td className="px-4 py-3 whitespace-nowrap">
                <Link href={`/matches/${m.id}`} className="text-foreground font-medium hover:text-gold">
                  <LocalTime sql={m.ended_at} />
                </Link>
              </td>
              <td className="px-4 py-3 text-text-muted">
                {mapHref(m) ? (
                  <Link href={mapHref(m)!} className="hover:text-gold">
                    {m.map_title ?? m.map_code}
                  </Link>
                ) : (
                  (m.map_title ?? m.map_code)
                )}
              </td>
              <td className="hidden md:table-cell px-4 py-3 text-text-muted">{GAME_TYPE_NAMES[m.game_type] ?? m.game_type}</td>
              {seat && m.player ? (
                <>
                  <td className={`px-4 py-3 font-semibold capitalize ${OUTCOME_STYLE[m.player.outcome ?? ""] ?? "text-text-dim"}`}>
                    {m.player.outcome ?? "abandoned"}
                  </td>
                  <td className="px-4 py-3 text-right text-text-muted">
                    <span className="inline-flex items-center gap-1.5">
                      <PlaceBadge place={m.player.place} />
                      <span className="text-xs">of {m.player_count}</span>
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right text-foreground">{m.player.score}</td>
                  <td className="px-4 py-3 text-right text-text-muted">
                    {m.player.kills} / {m.player.deaths}
                  </td>
                </>
              ) : (
                <>
                  <td className="px-4 py-3 text-foreground">
                    <Winner match={m} />
                    {m.team_game && m.red_score !== null && (
                      <span className="ml-2 text-xs font-semibold tabular-nums">
                        <span className={TEAM_TEXT.red}>{m.red_score}</span>
                        <span className="text-text-muted">–</span>
                        <span className={TEAM_TEXT.blue}>{m.blue_score}</span>
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right text-text-muted">{m.player_count}</td>
                </>
              )}
              <td className="hidden sm:table-cell px-4 py-3 text-right tabular-nums text-text-muted">{duration(m.duration_ms)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </TableFrame>
  );
}

/** Who won: the player's face and a link to their history, or the team's colour. */
function Winner({ match: m }: { match: MatchSummary }) {
  // winner_name is set only for a free-for-all win (a seat index).
  if (m.end_reason !== "abandoned" && m.winner_name) {
    return (
      <Link href={playerHref({ name: m.winner_name, user: m.winner_user })} className="inline-flex items-center gap-2 hover:text-gold">
        <PlayerAvatar name={m.winner_name} user={m.winner_user} ring={1} />
        {m.winner_name}
      </Link>
    );
  }
  const team = m.end_reason === "abandoned" ? null : m.winner;
  return (
    <span className={`inline-flex items-center gap-2 ${m.end_reason === "abandoned" ? "text-text-muted" : ""}`}>
      <TeamDot team={team} />
      {winnerText(m)}
    </span>
  );
}

/**
 * A career in a row of figures, plus the weapons that did the most. An
 * account's strip also carries its public report count; a bare in-game
 * name has no account to have been reported.
 */
export function PlayerTotalsStrip({ totals, reports }: { totals: PlayerTotals; reports?: number }) {
  const figures: [string, string, boolean?][] = [
    ["Matches", String(totals.matches)],
    ["Wins", String(totals.wins), true],
    ["Losses", String(totals.losses)],
    ["Kills", String(totals.kills)],
    ["Deaths", String(totals.deaths)],
    ["K/D", kd(totals.kills, totals.deaths), true],
  ];
  if (totals.captures > 0) figures.push(["Captures", String(totals.captures)]);
  if (reports !== undefined) figures.push(["Reports", String(reports)]);
  return (
    <div>
      <StatGrid className="md:grid-cols-4 xl:grid-cols-8">
        {figures.map(([label, value, accent]) => (
          <StatTile key={label} label={label} value={value} accent={accent} />
        ))}
      </StatGrid>
      {totals.weapons.length > 0 && (
        <p className="mt-4 text-sm text-text-muted">
          Most kills with:{" "}
          {totals.weapons.map((w, i) => (
            <span key={w.weapon}>
              {i > 0 && ", "}
              <span className="text-foreground">{weaponName(w.weapon)}</span> ({w.kills})
            </span>
          ))}
        </p>
      )}
    </div>
  );
}
