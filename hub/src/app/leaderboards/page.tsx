import Link from "next/link";
import { Search, Trophy } from "lucide-react";
import { getCloudflareContext } from "@opennextjs/cloudflare";

import { Footer } from "../components/Footer";
import { Navbar } from "../components/Navbar";
import { ButtonLink, EmptyState, FilterChips, PlayerAvatar } from "../components/ui";
import {
  BOARDS,
  MIN_KD_KILLS,
  MIN_KD_MATCHES,
  MIN_RATE_FINISHED,
  PERIODS,
  leaderboard,
  podiumSpokes,
  type Board,
  type Period,
  type Standing,
} from "@/lib/api/leaderboards";
import { withQuery } from "@/lib/filters";
import { marketingMetadata } from "@/lib/marketing";
import { kd } from "../matches/_components/format";
import { recordDisplay } from "../players/_components/font";
import { MiniRing } from "../players/_components/MiniRing";

export const metadata = marketingMetadata(
  "Halo Campaign Evolved Leaderboards | MJOLNIR Core",
  "Who leads Campaign Evolved multiplayer: most kills, best K/D, most wins and more, from public matches on the classic Halo CE maps.",
  "/leaderboards",
);

// Live data: never cached.
export const dynamic = "force-dynamic";

const BOARD_INFO: Record<Board, { label: string; unit: string; rule?: string }> = {
  kills: { label: "Kills", unit: "kills" },
  kd: { label: "K/D", unit: "kills per death", rule: `At least ${MIN_KD_KILLS} kills over ${MIN_KD_MATCHES} matches to place.` },
  wins: { label: "Wins", unit: "wins" },
  win_rate: { label: "Win rate", unit: "of finished matches won", rule: `At least ${MIN_RATE_FINISHED} finished matches to place.` },
  headshots: { label: "Headshots", unit: "headshot kills" },
  best_match: { label: "Best match", unit: "kills in one match" },
};

const PERIOD_LABEL: Record<Period, string> = { all: "All time", "30d": "30 days", "7d": "7 days" };

function shown(board: Board, value: number): string {
  if (board === "kd") return value.toFixed(2);
  if (board === "win_rate") return `${Math.round(value * 100)}%`;
  return value.toLocaleString("en-US");
}

/** The figures beside a row's headline: never the one the board already ranks by. */
function asideFacts(board: Board, s: Standing): string {
  const matches = `${s.matches} match${s.matches === 1 ? "" : "es"}`;
  if (board === "kd") return `${s.kills} kills · ${matches}`;
  if (board === "win_rate") return `${s.wins} of ${s.finished} finished`;
  if (board === "best_match") return s.best_match?.map_title ?? matches;
  return `${kd(s.kills, s.deaths)} K/D · ${matches}`;
}

const PLACE_TEXT = { 1: "text-gold", 2: "text-silver", 3: "text-bronze" } as const;

export default async function LeaderboardsPage({
  searchParams,
}: {
  searchParams: Promise<{ board?: string; period?: string }>;
}) {
  const params = await searchParams;
  const board: Board = BOARDS.includes(params.board as Board) ? (params.board as Board) : "kills";
  const period: Period = PERIODS.includes(params.period as Period) ? (params.period as Period) : "all";
  const { env } = getCloudflareContext();
  const db = env.DB as never;
  const { standings, matches } = await leaderboard(db, board, period);
  const top = standings.slice(0, 3);
  const rest = standings.slice(3);
  const rings = await podiumSpokes(db, top.map((s) => s.user.id));
  const peak = standings[0]?.value || 1;
  const info = BOARD_INFO[board];
  const href = (over: { board?: Board; period?: Period }) => {
    const b = over.board ?? board;
    const p = over.period ?? period;
    return withQuery("/leaderboards", { board: b === "kills" ? undefined : b, period: p === "all" ? undefined : p });
  };

  return (
    <div className={recordDisplay.variable}>
      <Navbar />
      <main id="main">
        <header className="record-hero relative overflow-hidden pb-10 pt-44 sm:pt-32">
          <div className="relative mx-auto flex max-w-6xl flex-wrap items-end justify-between gap-6 px-4 sm:px-6">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-text-muted">Public matches</p>
              <h1 className="record-display mt-3 text-[clamp(3.25rem,9vw,7rem)] leading-[0.92] text-foreground">Leaderboards</h1>
            </div>
            <form action="/players" role="search" className="relative w-full sm:w-64">
              <label htmlFor="leaderboard-search" className="sr-only">Find a player</label>
              <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted" />
              <input
                id="leaderboard-search"
                name="name"
                type="search"
                placeholder="Find a player"
                maxLength={64}
                autoComplete="off"
                className="min-h-10 w-full rounded-lg border border-border bg-surface pl-9 pr-3 text-sm text-foreground placeholder:text-text-muted hover:border-border-bright focus:border-gold/60"
              />
            </form>
          </div>
        </header>

        <div className="mx-auto max-w-6xl px-4 pb-20 sm:px-6">
          <div className="flex flex-col gap-3 border-b border-border pb-5 lg:flex-row lg:items-center lg:justify-between">
            <FilterChips
              label="Leaderboard"
              options={BOARDS.map((b) => ({ label: BOARD_INFO[b].label, href: href({ board: b }), active: b === board }))}
            />
            <FilterChips
              label="Period"
              options={PERIODS.map((p) => ({ label: PERIOD_LABEL[p], href: href({ period: p }), active: p === period }))}
            />
          </div>

          {standings.length === 0 ? (
            <div className="mt-10">
              <EmptyState
                icon={Trophy}
                title="Nobody has placed here yet"
                action={period === "all" ? <ButtonLink href="/multiplayer">Get multiplayer</ButtonLink> : <ButtonLink href={href({ period: "all" })}>See all time</ButtonLink>}
              >
                {info.rule ?? "Public matches with two hub accounts in them count here."}
              </EmptyState>
            </div>
          ) : (
            <>
              <ol className="mt-12 grid gap-6 sm:grid-cols-3 sm:items-end">
                {top.map((s, i) => (
                  <li key={s.user.id} className={i === 0 ? "sm:order-2" : i === 1 ? "sm:order-1" : "sm:order-3"}>
                    <Link href={`/users/${s.user.id}`} className="group block text-center">
                      <div className={`mx-auto ${i === 0 ? "max-w-[320px]" : "max-w-[240px]"}`}>
                        <MiniRing
                          matches={rings[s.user.id] ?? []}
                          center={<PlayerAvatar name={s.user.name} user={s.user} size={i === 0 ? "xl" : "lg"} />}
                        />
                      </div>
                      <p className={`record-display mt-1 text-5xl leading-none ${PLACE_TEXT[s.rank as 1 | 2 | 3] ?? "text-foreground"}`}>
                        <span className="sr-only">Place </span>{s.rank}
                      </p>
                      <p className="mt-2 truncate text-lg font-semibold text-foreground group-hover:text-gold">{s.user.name}</p>
                      <p className="record-display text-4xl leading-tight text-foreground tabular-nums">{shown(board, s.value)}</p>
                      <p className="text-xs text-text-muted">{info.unit}</p>
                      <p className="mt-1 text-xs text-text-dim">{asideFacts(board, s)}</p>
                    </Link>
                  </li>
                ))}
              </ol>

              {rest.length > 0 && (
                <ol className="mt-12 divide-y divide-border border-y border-border">
                  {rest.map((s) => (
                    <li key={s.user.id}>
                      <Link
                        href={`/users/${s.user.id}`}
                        className="grid grid-cols-[2.5rem_minmax(0,1fr)_auto] items-center gap-3 py-3 hover:bg-surface-hover/40 sm:grid-cols-[3rem_minmax(0,14rem)_minmax(0,1fr)_auto] sm:gap-5 sm:px-2"
                      >
                        <span className="record-display text-3xl leading-none text-text-muted tabular-nums">{s.rank}</span>
                        <span className="flex min-w-0 items-center gap-3">
                          <PlayerAvatar name={s.user.name} user={s.user} size="md" />
                          <span className="min-w-0">
                            <span className="block truncate text-sm font-semibold text-foreground">{s.user.name}</span>
                            <span className="block truncate text-xs text-text-dim">{asideFacts(board, s)}</span>
                          </span>
                        </span>
                        <span aria-hidden className="hidden h-1 rounded-full bg-border sm:block">
                          <span className="block h-full rounded-full bg-gold" style={{ width: `${(s.value / peak) * 100}%` }} />
                        </span>
                        <span className="record-display text-3xl leading-none text-foreground tabular-nums">{shown(board, s.value)}</span>
                      </Link>
                    </li>
                  ))}
                </ol>
              )}

              <p className="mt-6 max-w-2xl text-xs leading-relaxed text-text-dim">
                {info.rule && <>{info.rule} </>}
                From {matches} public match{matches === 1 ? "" : "es"}, as their hosts reported them. A match counts when at
                least two hub accounts played in it, so a board can read lower than a career total on a profile. Link your
                account from the game to place.
              </p>
            </>
          )}
        </div>
      </main>
      <Footer />
    </div>
  );
}
