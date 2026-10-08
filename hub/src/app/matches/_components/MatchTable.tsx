import Link from "next/link";
import { Swords } from "lucide-react";

import { GAME_TYPE_NAMES } from "@/kit/types";
import type { MatchSummary, PlayerTotals } from "@/lib/api/matches";
import { Avatar } from "./Avatar";
import { LocalTime } from "./LocalTime";
import { duration, kd, mapHref, playerHref, weaponName, winnerText } from "./format";

const TEAM_DOT: Record<string, string> = {
  red: "bg-red-500",
  blue: "bg-sky-500",
};

const OUTCOME_STYLE: Record<string, string> = {
  win: "text-emerald-400",
  loss: "text-red-400",
  draw: "text-text-muted",
};

/**
 * A list of matches. With `seat`, each row carries that player's line
 * (place, score, kills/deaths, outcome) instead of the match's winner.
 */
export function MatchTable({ matches, seat = false }: { matches: MatchSummary[]; seat?: boolean }) {
  if (matches.length === 0) {
    return (
      <div className="flex items-center gap-3 text-text-muted">
        <Swords className="w-5 h-5" />
        <p>No matches yet. Public games report each match here when it ends.</p>
      </div>
    );
  }
  return (
    <div className="overflow-x-auto rounded-xl border border-border">
      <table className="w-full text-sm">
        <thead className="bg-surface-raised text-text-dim text-xs uppercase tracking-wide">
          <tr>
            <th className="text-left px-4 py-3">Played</th>
            <th className="text-left px-4 py-3">Map</th>
            <th className="text-left px-4 py-3">Game type</th>
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
            <th className="text-right px-4 py-3">Length</th>
          </tr>
        </thead>
        <tbody>
          {matches.map((m) => (
            <tr key={m.id} className="border-t border-border hover:bg-surface-raised/50">
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
              <td className="px-4 py-3 text-text-muted">{GAME_TYPE_NAMES[m.game_type] ?? m.game_type}</td>
              {seat && m.player ? (
                <>
                  <td className={`px-4 py-3 font-semibold capitalize ${OUTCOME_STYLE[m.player.outcome ?? ""] ?? "text-text-dim"}`}>
                    {m.player.outcome ?? "abandoned"}
                  </td>
                  <td className="px-4 py-3 text-right text-text-muted">
                    {m.player.place} / {m.player_count}
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
                      <span className="ml-2 text-xs text-text-dim">
                        {m.red_score}–{m.blue_score}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-right text-text-muted">{m.player_count}</td>
                </>
              )}
              <td className="px-4 py-3 text-right text-text-muted">{duration(m.duration_ms)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Who won: the player's face and a link to their history, or the team's colour. */
function Winner({ match: m }: { match: MatchSummary }) {
  // winner_name is set only for a free-for-all win (a seat index).
  if (m.end_reason !== "abandoned" && m.winner_name) {
    return (
      <Link href={playerHref({ name: m.winner_name, user: m.winner_user })} className="inline-flex items-center gap-2 hover:text-gold">
        <Avatar name={m.winner_name} user={m.winner_user} />
        {m.winner_name}
      </Link>
    );
  }
  const dot = m.end_reason === "abandoned" ? undefined : TEAM_DOT[m.winner ?? ""];
  return (
    <span className="inline-flex items-center gap-2">
      {dot && <span className={`inline-block w-2.5 h-2.5 rounded-full ${dot}`} />}
      {winnerText(m)}
    </span>
  );
}

/** A career in a row of figures, plus the weapons that did the most. */
export function PlayerTotalsStrip({ totals }: { totals: PlayerTotals }) {
  const figures: [string, string][] = [
    ["Matches", String(totals.matches)],
    ["Wins", String(totals.wins)],
    ["Losses", String(totals.losses)],
    ["Kills", String(totals.kills)],
    ["Deaths", String(totals.deaths)],
    ["K/D", kd(totals.kills, totals.deaths)],
  ];
  if (totals.captures > 0) figures.push(["Captures", String(totals.captures)]);
  return (
    <div>
      <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-7 gap-3">
        {figures.map(([label, value]) => (
          <div key={label} className="rounded-xl border border-border bg-surface px-4 py-3">
            <div className="text-[11px] uppercase tracking-wide text-text-dim">{label}</div>
            <div className="text-xl font-bold text-foreground">{value}</div>
          </div>
        ))}
      </div>
      {totals.weapons.length > 0 && (
        <p className="mt-3 text-sm text-text-muted">
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
