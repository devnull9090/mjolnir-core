import { cache } from "react";
import Link from "next/link";
import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { getCloudflareContext } from "@opennextjs/cloudflare";

import { Navbar } from "../../components/Navbar";
import { Footer } from "../../components/Footer";
import { getMatch } from "@/lib/api/matches";
import type { MatchDetail, MatchPlayer } from "@/lib/api/matches";
import { GAME_TYPE_NAMES } from "@/kit/types";
import {
  duration,
  eventLine,
  explainedDeaths,
  isExplainedDeath,
  kd,
  namer,
  when,
  winnerText,
} from "../_components/format";
import { PositionMap } from "../_components/PositionMap";

/**
 * One match: the final scoreboard, the timeline of what happened, and where
 * the kills and deaths were. Seats link to their player's history: the hub
 * account's when the seat is linked, the in-game name's otherwise.
 */
const loadMatch = cache((id: string) => {
  const { env } = getCloudflareContext();
  return getMatch(env.DB as never, id);
});

export const dynamic = "force-dynamic";

function title(m: MatchDetail): string {
  return `${GAME_TYPE_NAMES[m.game_type] ?? m.game_type} on ${m.map_title ?? m.map_code}`;
}

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const match = await loadMatch((await params).id);
  if (!match) return { title: "Match | MJOLNIR Core" };
  return {
    title: `${title(match)} · ${winnerText(match)} | MJOLNIR Core`,
    description: `${title(match)}, ${match.player_count} players, ${duration(match.duration_ms)}. ${winnerText(match)}.`,
    robots: { index: false },
  };
}

const TEAM_STYLE: Record<string, string> = {
  red: "border-l-red-500",
  blue: "border-l-sky-500",
};

function playerHref(p: MatchPlayer): string {
  return p.user ? `/users/${p.user.id}` : `/players/${encodeURIComponent(p.name)}`;
}

function Scoreboard({ match, focus }: { match: MatchDetail; focus: number | null }) {
  const groups: { label: string | null; team: string | null; players: MatchPlayer[]; total: number | null }[] =
    match.team_game
      ? (["red", "blue"] as const).map((team) => ({
          label: team === "red" ? "Red team" : "Blue team",
          team,
          players: match.players.filter((p) => p.team === team),
          total: team === "red" ? match.red_score : match.blue_score,
        }))
      : [{ label: null, team: null, players: match.players, total: null }];
  if (match.team_game) {
    const loose = match.players.filter((p) => !p.team);
    if (loose.length) groups.push({ label: "No team", team: null, players: loose, total: null });
  }
  return (
    <div className="overflow-x-auto rounded-xl border border-border">
      <table className="w-full text-sm">
        <thead className="bg-surface-raised text-text-dim text-xs uppercase tracking-wide">
          <tr>
            <th className="text-left px-4 py-3">Player</th>
            <th className="text-right px-4 py-3">{match.game_type === "ctf" ? "Captures" : "Score"}</th>
            <th className="text-right px-4 py-3">Kills</th>
            <th className="text-right px-4 py-3">Deaths</th>
            <th className="text-right px-4 py-3">Suicides</th>
            <th className="text-right px-4 py-3">K/D</th>
            <th className="text-right px-4 py-3">Map</th>
          </tr>
        </thead>
        {groups.map((g) => (
          <tbody key={g.label ?? "all"}>
            {g.label && (
              <tr className="border-t border-border bg-surface-raised/60">
                <td
                  colSpan={7}
                  className={`px-4 py-2 text-xs font-bold uppercase tracking-wide text-foreground border-l-4 ${TEAM_STYLE[g.team ?? ""] ?? "border-l-transparent"}`}
                >
                  {g.label}
                  {g.total !== null && <span className="ml-2 text-text-muted">{g.total}</span>}
                </td>
              </tr>
            )}
            {g.players.map((p) => (
              <tr key={p.index} className={`border-t border-border ${focus === p.index ? "bg-gold/10" : ""}`}>
                <td className={`px-4 py-3 border-l-4 ${TEAM_STYLE[p.team ?? ""] ?? "border-l-transparent"}`}>
                  <span className="text-text-dim mr-2 tabular-nums">{p.place}.</span>
                  <Link href={playerHref(p)} className="text-foreground font-medium hover:text-gold">
                    {p.name}
                  </Link>
                  {p.user && (
                    <span className="ml-2 text-[11px] text-text-dim" title="Linked to a hub account">
                      @{p.user.name}
                    </span>
                  )}
                  {p.is_host && <span className="ml-2 text-[11px] text-gold">host</span>}
                  {p.left_early && <span className="ml-2 text-[11px] text-text-dim">left</span>}
                  {p.outcome === "win" && <span className="ml-2 text-[11px] text-emerald-400">winner</span>}
                </td>
                <td className="px-4 py-3 text-right text-foreground font-semibold">{p.score}</td>
                <td className="px-4 py-3 text-right text-text-muted">{p.kills}</td>
                <td className="px-4 py-3 text-right text-text-muted">{p.deaths}</td>
                <td className="px-4 py-3 text-right text-text-muted">{p.suicides}</td>
                <td className="px-4 py-3 text-right text-text-muted">{kd(p.kills, p.deaths)}</td>
                <td className="px-4 py-3 text-right">
                  <Link
                    href={focus === p.index ? `/matches/${match.id}#map` : `/matches/${match.id}?p=${p.index}#map`}
                    className="text-xs text-text-dim hover:text-gold"
                  >
                    {focus === p.index ? "all" : "show"}
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        ))}
      </table>
    </div>
  );
}

export default async function MatchPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ p?: string }>;
}) {
  const match = await loadMatch((await params).id);
  if (!match) notFound();
  const { p } = await searchParams;
  const focus =
    p !== undefined && /^\d{1,2}$/.test(p) && match.players.some((x) => x.index === Number(p)) ? Number(p) : null;
  const nameOf = namer(match.players);
  const explained = explainedDeaths(match.events);
  const lines = match.events
    .map((e) => ({ e, text: isExplainedDeath(e, explained) ? null : eventLine(e, nameOf) }))
    .filter((l): l is { e: (typeof match.events)[number]; text: string } => l.text !== null);
  const other = match.events.length - lines.length;

  return (
    <>
      <Navbar />

      <main className="pt-32 md:pt-36 pb-16 px-6 max-w-6xl mx-auto">
        <div className="mb-8">
          <Link href="/matches" className="text-xs text-text-dim hover:text-foreground">
            ← Match history
          </Link>
          <h1 className="mt-2 text-3xl md:text-4xl font-black text-foreground">{title(match)}</h1>
          <p className="mt-2 text-text-muted">
            {when(match.ended_at)} · {duration(match.duration_ms)} · {match.player_count} players · hosted by{" "}
            {match.host}
            {match.score_to_win ? ` · first to ${match.score_to_win}` : ""}
          </p>
          <p className="mt-3 text-xl font-bold text-gold">
            {match.end_reason === "abandoned"
              ? "Abandoned before the end"
              : `${winnerText(match)}${match.winner === "draw" ? "" : " won"}`}
            {match.team_game && match.red_score !== null && (
              <span className="ml-3 text-base font-semibold text-text-muted">
                <span className="text-red-400">{match.red_score}</span> –{" "}
                <span className="text-sky-400">{match.blue_score}</span>
              </span>
            )}
          </p>
        </div>

        <section className="mb-10">
          <Scoreboard match={match} focus={focus} />
        </section>

        <div className="grid gap-10 lg:grid-cols-2">
          <section id="map">
            <h2 className="text-sm font-bold uppercase text-text-dim mb-3">
              Kills and deaths{focus !== null ? ` · ${nameOf(focus)}` : ""}
            </h2>
            <PositionMap events={match.events} nameOf={nameOf} focus={focus} />
          </section>

          <section>
            <h2 className="text-sm font-bold uppercase text-text-dim mb-3">Timeline</h2>
            {lines.length === 0 ? (
              <p className="text-sm text-text-muted">Nothing happened.</p>
            ) : (
              <ol className="max-h-[560px] overflow-y-auto rounded-xl border border-border divide-y divide-border text-sm">
                {lines.map(({ e, text }) => (
                  <li
                    key={e.seq}
                    className={`flex gap-3 px-4 py-2 ${focus !== null && (e.cause === focus || e.effect === focus) ? "bg-gold/10" : ""}`}
                  >
                    <span className="w-12 shrink-0 tabular-nums text-text-dim">{duration(e.t_ms)}</span>
                    <span
                      className={
                        e.type === "kill" || e.type === "suicide" || e.type === "death"
                          ? "text-foreground"
                          : "text-text-muted"
                      }
                    >
                      {text}
                    </span>
                  </li>
                ))}
              </ol>
            )}
            {other > 0 && (
              <p className="mt-2 text-xs text-text-dim">
                Plus {other} other incidents (spawns, deaths a kill already tells, commendations, lead changes)
                in the{" "}
                <a href={`/api/v1/matches/${match.id}`} className="underline hover:text-foreground">
                  full event data
                </a>
                .
              </p>
            )}
          </section>
        </div>
      </main>

      <Footer />
    </>
  );
}
