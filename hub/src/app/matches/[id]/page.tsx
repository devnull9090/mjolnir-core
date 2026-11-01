import { cache } from "react";
import Link from "next/link";
import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { ArrowLeft, Clock, Crown, Flag, Users } from "lucide-react";
import { getCloudflareContext } from "@opennextjs/cloudflare";

import { PageShell, PlaceBadge, PlayerAvatar, Pill, SectionHeading, TableFrame, TEAM_BORDER, TEAM_TEXT } from "../../components/ui";
import { getMatch } from "@/lib/api/matches";
import type { MatchDetail, MatchPlayer } from "@/lib/api/matches";
import { GAME_TYPE_NAMES } from "@/kit/types";
import {
  duration,
  eventLine,
  explainedDeaths,
  isExplainedDeath,
  kd,
  mapHref,
  namer,
  playerHref,
  winnerText,
} from "../_components/format";
import { LocalTime } from "../_components/LocalTime";
import { MatchReplay } from "../_components/MatchReplay";
import { Podium } from "../_components/Podium";
import { positionMarks } from "../_components/positions";
import mapPreviews from "../_components/map-previews.json";

/**
 * One match: the final scoreboard, the timeline of what happened, where
 * the kills and deaths were, and what the players said. Seats link to their player's history: the hub
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

/**
 * What players said, in order. A line names a hub account only when it is
 * the one linked to the sender's seat; otherwise the in-game name.
 */
function Chat({ match }: { match: MatchDetail }) {
  if (!match.chat.length) return null;
  return (
    <section aria-labelledby="chat" className="mt-12">
      <SectionHeading id="chat">Chat · {match.chat.length}</SectionHeading>
      <div
        tabIndex={0}
        role="log"
        aria-labelledby="chat"
        className="max-h-[32rem] overflow-y-auto rounded-xl border border-border bg-surface px-4 py-3 text-sm space-y-1"
      >
        {match.chat.map((l, i) => {
          const colour = match.team_game ? (TEAM_TEXT[l.team ?? ""] ?? "text-foreground") : "text-foreground";
          const who = l.user ? l.user.name : l.name;
          return (
            <div key={i} className="flex gap-3">
              <span className="w-12 shrink-0 text-right text-text-muted tabular-nums">{duration(l.t_ms)}</span>
              <span className="min-w-0 break-words">
                {l.channel === "team" && <span className="mr-1.5 text-[11px] font-bold text-text-muted">[TEAM]</span>}
                {l.index >= 0 ? (
                  <Link
                    href={playerHref(l)}
                    title={l.user ? `In game: ${l.name}` : undefined}
                    className={`inline-flex items-center gap-1.5 align-middle font-semibold hover:underline ${colour}`}
                  >
                    {l.user && <PlayerAvatar name={l.name} user={l.user} size="xs" />}
                    {who}
                  </Link>
                ) : (
                  <span className="font-semibold text-text-muted">{who}</span>
                )}
                <span className="text-text-muted">: </span>
                <span className="text-text-muted whitespace-pre-wrap">{l.text}</span>
              </span>
            </div>
          );
        })}
      </div>
    </section>
  );
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
  // Medal rings only where a place was earned: a match nobody scored in has
  // everyone tied for first.
  const ranked = match.players.some((p) => p.score !== 0);
  return (
    <TableFrame>
      <table className="w-full text-sm">
        <caption className="sr-only">Final scoreboard</caption>
        <thead className="bg-surface-raised text-text-muted text-xs uppercase tracking-wide">
          <tr>
            <th scope="col" className="text-left px-4 py-3">Player</th>
            <th scope="col" className="text-right px-4 py-3">{match.game_type === "ctf" ? "Captures" : "Score"}</th>
            <th scope="col" className="text-right px-4 py-3">Kills</th>
            <th scope="col" className="text-right px-4 py-3">Deaths</th>
            <th scope="col" className="hidden sm:table-cell text-right px-4 py-3">Suicides</th>
            <th scope="col" className="text-right px-4 py-3">K/D</th>
            <th scope="col" className="text-right px-4 py-3">
              <span className="sr-only">On the map</span>
            </th>
          </tr>
        </thead>
        {groups.map((g) => (
          <tbody key={g.label ?? "all"}>
            {g.label && (
              <tr className="border-t border-border bg-surface-raised/60">
                <th
                  scope="colgroup"
                  colSpan={7}
                  className={`px-4 py-2 text-left text-xs font-bold uppercase tracking-wide border-l-4 ${TEAM_BORDER[g.team ?? ""] ?? "border-l-transparent"} ${TEAM_TEXT[g.team ?? ""] ?? "text-foreground"}`}
                >
                  {g.label}
                  {g.total !== null && <span className="ml-2 text-foreground tabular-nums">{g.total}</span>}
                </th>
              </tr>
            )}
            {g.players.map((p) => (
              <tr key={p.index} className={`border-t border-border ${focus === p.index ? "bg-gold/10" : ""}`}>
                <td className={`px-4 py-3 border-l-4 ${TEAM_BORDER[p.team ?? ""] ?? "border-l-transparent"}`}>
                  <div className="flex items-center gap-3">
                    {ranked && <PlaceBadge place={p.place} />}
                    <Link
                      href={playerHref(p)}
                      className="inline-flex min-w-0 items-center gap-2 font-semibold text-foreground hover:text-gold"
                    >
                      <PlayerAvatar
                        name={p.name}
                        user={p.user}
                        size="md"
                        ring={ranked && p.place <= 3 ? (p.place as 1 | 2 | 3) : undefined}
                      />
                      <span className="min-w-0">
                        <span className="block truncate">{p.name}</span>
                        {p.user && (
                          <span className="block text-[11px] font-normal text-text-muted">
                            <span className="sr-only">Hub account </span>@{p.user.name}
                          </span>
                        )}
                      </span>
                    </Link>
                    <span className="hidden flex-wrap gap-1 sm:flex">
                      {p.outcome === "win" && (
                        <Pill tone="gold">
                          <Crown aria-hidden className="h-3 w-3" />
                          Winner
                        </Pill>
                      )}
                      {p.is_host && <Pill>Host</Pill>}
                      {p.left_early && <Pill>Left</Pill>}
                    </span>
                  </div>
                </td>
                <td className="px-4 py-3 text-right text-base font-black tabular-nums text-foreground">{p.score}</td>
                <td className="px-4 py-3 text-right tabular-nums text-text-muted">{p.kills}</td>
                <td className="px-4 py-3 text-right tabular-nums text-text-muted">{p.deaths}</td>
                <td className="hidden sm:table-cell px-4 py-3 text-right tabular-nums text-text-muted">{p.suicides}</td>
                <td className="px-4 py-3 text-right tabular-nums text-text-muted">{kd(p.kills, p.deaths)}</td>
                <td className="px-4 py-3 text-right">
                  <Link
                    href={focus === p.index ? `/matches/${match.id}#map` : `/matches/${match.id}?p=${p.index}#map`}
                    aria-label={focus === p.index ? "Show everyone on the map" : `Show ${p.name} on the map`}
                    className="inline-flex min-h-8 items-center rounded-md border border-border px-2.5 text-xs text-text-muted transition-colors hover:border-gold/40 hover:text-gold"
                  >
                    {focus === p.index ? "All" : "Map"}
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        ))}
      </table>
    </TableFrame>
  );
}

/** The hero's verdict: the winner's face, the team score, or how it ended. */
function Result({ match }: { match: MatchDetail }) {
  const abandoned = match.end_reason === "abandoned";
  const panel = "shrink-0 rounded-2xl border bg-background/70 backdrop-blur";
  if (match.team_game && match.red_score !== null && match.blue_score !== null) {
    const won = abandoned ? null : match.winner;
    const side = (team: "red" | "blue", score: number) => (
      <div className="text-center">
        <p className={`text-xs font-bold uppercase tracking-widest ${TEAM_TEXT[team]}`}>{team}</p>
        <p className={`text-5xl md:text-6xl font-black tabular-nums ${won === team ? "text-foreground" : "text-text-muted"}`}>
          {score}
        </p>
      </div>
    );
    return (
      <div className={`${panel} flex flex-col items-center gap-2 border-border px-6 py-4`}>
        <div className="flex items-center gap-5">
          {side("red", match.red_score)}
          <span aria-hidden className="text-lg font-bold text-text-muted">
            –
          </span>
          {side("blue", match.blue_score)}
        </div>
        <p className="text-sm font-bold text-gold">
          {abandoned ? "Abandoned before the end" : `${winnerText(match)}${match.winner === "draw" ? "" : " wins"}`}
        </p>
      </div>
    );
  }
  const winner = abandoned ? undefined : match.players.find((x) => x.outcome === "win");
  if (winner) {
    return (
      <div className={`${panel} flex items-center gap-4 border-gold/40 p-4 pr-6`}>
        <PlayerAvatar name={winner.name} user={winner.user} size="lg" ring={1} />
        <div className="min-w-0">
          <p className="inline-flex items-center gap-1 text-xs font-bold uppercase tracking-widest text-gold">
            <Crown aria-hidden className="h-3.5 w-3.5" />
            Winner
          </p>
          <p className="truncate text-2xl font-black text-foreground">{winner.name}</p>
          <p className="text-sm text-text-muted">
            {winner.score} score · {winner.kills} kills
          </p>
        </div>
      </div>
    );
  }
  return (
    <p className={`${panel} border-border px-5 py-3 text-lg font-bold text-text-muted`}>
      {abandoned ? "Abandoned before the end" : winnerText(match)}
    </p>
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
  const { kills, deaths } = positionMarks(match.events, nameOf, focus);
  const rows = lines.map(({ e, text }) => ({
    seq: e.seq,
    t_ms: e.t_ms,
    text,
    strong: e.type === "kill" || e.type === "suicide" || e.type === "death",
    mine: focus !== null && (e.cause === focus || e.effect === focus),
  }));
  const mapName = match.map_title ?? match.map_code;
  const mode = GAME_TYPE_NAMES[match.game_type] ?? match.game_type;

  return (
    <PageShell>
      <Link
        href="/matches"
        className="mb-4 inline-flex items-center gap-1.5 text-sm text-text-muted transition-colors hover:text-foreground"
      >
        <ArrowLeft aria-hidden className="h-4 w-4" />
        Match history
      </Link>

      <header className="relative mb-10 overflow-hidden rounded-3xl border border-border bg-surface">
        {match.map_cover_url && (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={match.map_cover_url}
            alt=""
            width={1280}
            height={720}
            fetchPriority="high"
            className="absolute inset-0 h-full w-full object-cover opacity-60"
          />
        )}
        <div aria-hidden className="absolute inset-0 bg-gradient-to-r from-background via-background/80 to-background/20" />
        <div aria-hidden className="absolute inset-0 bg-gradient-to-t from-background/90 to-transparent" />
        <div className="relative flex flex-col gap-8 p-6 sm:p-8 md:p-10 lg:flex-row lg:items-end lg:justify-between">
          <div className="min-w-0">
            <div className="mb-3 flex flex-wrap gap-2">
              <Pill tone="gold">{mode}</Pill>
              {match.end_reason === "abandoned" && <Pill>Abandoned</Pill>}
            </div>
            <h1 className="text-3xl font-black tracking-tight text-foreground text-balance sm:text-4xl md:text-5xl">
              {mode} on{" "}
              {mapHref(match) ? (
                <Link href={mapHref(match)!} className="underline decoration-gold/40 underline-offset-4 hover:text-gold">
                  {mapName}
                </Link>
              ) : (
                mapName
              )}
            </h1>
            <ul className="mt-4 flex flex-wrap gap-x-5 gap-y-2 text-sm text-text-muted">
              <li>
                <LocalTime sql={match.ended_at} />
              </li>
              <li className="inline-flex items-center gap-1.5">
                <Clock aria-hidden className="h-4 w-4" />
                {duration(match.duration_ms)}
              </li>
              <li className="inline-flex items-center gap-1.5">
                <Users aria-hidden className="h-4 w-4" />
                {match.player_count} players
              </li>
              {match.score_to_win ? (
                <li className="inline-flex items-center gap-1.5">
                  <Flag aria-hidden className="h-4 w-4" />
                  First to {match.score_to_win}
                </li>
              ) : null}
              <li>Hosted by {match.host}</li>
            </ul>
          </div>
          <Result match={match} />
        </div>
      </header>

      {!match.team_game && match.end_reason !== "abandoned" && <Podium players={match.players} />}

      <section aria-labelledby="scoreboard" className="my-12">
        <SectionHeading id="scoreboard">Scoreboard</SectionHeading>
        <Scoreboard match={match} focus={focus} />
      </section>

      <MatchReplay
        code={match.map_code in mapPreviews ? match.map_code : null}
        kills={kills}
        deaths={deaths}
        rows={rows}
        durationMs={match.duration_ms}
        mapHeading={`Kills and deaths${focus !== null ? ` · ${nameOf(focus)}` : ""}`}
        matchId={match.id}
        otherCount={other}
      />

      <Chat match={match} />
    </PageShell>
  );
}
