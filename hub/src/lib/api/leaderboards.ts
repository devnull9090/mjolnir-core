/**
 * The leaderboards: hub accounts ranked over public matches.
 *
 * Two rules decide what counts, and both are about trust (docs/match_stats.md):
 *
 * - Only a linked seat ranks. Anyone can play under any name, so a name on a
 *   board would be a way to wear someone else's record. A seat is linked by
 *   the player's own game claiming it.
 * - Only a match with two linked seats counts. A report is its host's word,
 *   and a host alone (or alone with AI bots) could otherwise fill the board.
 *
 * So a board reads lower than a career total on a profile, on purpose.
 */
import { linkedUser, type Db, type Row } from "./matches";
import type { RecordMatch } from "./player-record";

/** Linked seats a match needs to count. */
export const MIN_LINKED_SEATS = 2;
/** Below these, a K/D says more about one good game than about the player. */
export const MIN_KD_KILLS = 20;
export const MIN_KD_MATCHES = 3;
/** Finished matches a win rate needs. */
export const MIN_RATE_FINISHED = 3;
/** Rows on a board. */
const BOARD_ROWS = 50;
/** Spokes on a podium ring: enough to show a shape at that size. */
const PODIUM_SPOKES = 60;

export const BOARDS = ["kills", "kd", "wins", "win_rate", "headshots", "best_match"] as const;
export type Board = (typeof BOARDS)[number];

export const PERIODS = ["all", "30d", "7d"] as const;
export type Period = (typeof PERIODS)[number];

/** Fixed strings, never request text: these go straight into the SQL. */
const SINCE: Record<Period, string> = {
  all: "",
  "30d": `AND m.ended_at >= datetime('now', '-30 days')`,
  "7d": `AND m.ended_at >= datetime('now', '-7 days')`,
};

const KD = `CAST(SUM(p.kills) AS REAL) / MAX(SUM(p.deaths), 1)`;
const WIN_RATE = `CAST(SUM(p.outcome = 'win') AS REAL) / MAX(SUM(p.outcome IS NOT NULL), 1)`;

/** What each board sorts by, and who is on it. Fixed strings, as above. */
const ORDER: Record<Board, { value: string; having: string }> = {
  kills: { value: `SUM(p.kills)`, having: `SUM(p.kills) > 0` },
  kd: { value: KD, having: `SUM(p.kills) >= ${MIN_KD_KILLS} AND COUNT(*) >= ${MIN_KD_MATCHES}` },
  wins: { value: `SUM(p.outcome = 'win')`, having: `SUM(p.outcome = 'win') > 0` },
  win_rate: { value: WIN_RATE, having: `SUM(p.outcome IS NOT NULL) >= ${MIN_RATE_FINISHED}` },
  headshots: { value: `SUM(COALESCE(hs.n, 0))`, having: `SUM(COALESCE(hs.n, 0)) > 0` },
  best_match: { value: `MAX(p.kills)`, having: `MAX(p.kills) > 0` },
};

export interface Standing {
  /** Shared on a tie: 1, 2, 2, 4. */
  rank: number;
  user: { id: string; name: string; avatar_url: string | null };
  /** What the board ranks by. */
  value: number;
  matches: number;
  kills: number;
  deaths: number;
  wins: number;
  finished: number;
  /** Only a best-match board fills these. */
  best_match: { id: string; map_title: string | null } | null;
}

export interface Leaderboard {
  standings: Standing[];
  /** Matches that counted in this period. */
  matches: number;
}

const num = (v: unknown) => (typeof v === "number" ? v : 0);

/** The matches a board counts, as a CTE. */
function counted(period: Period) {
  return `WITH counted AS (
    SELECT m.id, m.map_code
    FROM matches m
    WHERE (SELECT COUNT(*) FROM match_players q
           WHERE q.match_id = m.id AND q.user_id IS NOT NULL) >= ${MIN_LINKED_SEATS}
      AND EXISTS (SELECT 1 FROM match_players q WHERE q.match_id = m.id AND (q.score <> 0 OR q.kills > 0))
      ${SINCE[period]}
  )`;
}

export async function leaderboard(db: Db, board: Board, period: Period): Promise<Leaderboard> {
  const { value, having } = ORDER[board];
  const headshots =
    board === "headshots"
      ? `LEFT JOIN (
           SELECT hp.match_id, hp.player_index, COUNT(*) AS n
           FROM counted c
           JOIN match_players hp ON hp.match_id = c.id AND hp.user_id IS NOT NULL
           JOIN match_events e ON e.match_id = hp.match_id AND e.cause = hp.player_index
           WHERE e.type = 'kill' AND e.modifier = 1 AND e.effect <> hp.player_index
           GROUP BY hp.match_id, hp.player_index
         ) hs ON hs.match_id = p.match_id AND hs.player_index = p.player_index`
      : "";
  // SQLite takes a bare column from the row a lone MAX() picked, which is how
  // a best-match board knows which match it was.
  const bestColumns = board === "best_match" ? `, c.id AS best_id, ml.title AS best_map` : "";
  const bestJoin = board === "best_match" ? `LEFT JOIN map_listings ml ON ml.code = c.map_code` : "";

  const [rows, total] = await db.batch([
    db.prepare(
      `${counted(period)}
       SELECT ${value} AS value, COUNT(*) AS matches,
              SUM(p.kills) AS kills, SUM(p.deaths) AS deaths,
              SUM(p.outcome = 'win') AS wins, SUM(p.outcome IS NOT NULL) AS finished,
              u.id AS u_id, u.display_name AS u_display_name, u.discord_username AS u_username,
              u.discord_id AS u_discord_id, u.discord_avatar AS u_avatar${bestColumns}
       FROM counted c
       JOIN match_players p ON p.match_id = c.id
       JOIN users u ON u.id = p.user_id AND u.banned_at IS NULL
       ${headshots}
       ${bestJoin}
       GROUP BY p.user_id
       HAVING ${having}
       ORDER BY value DESC, SUM(p.kills) DESC, u.id
       LIMIT ${BOARD_ROWS}`,
    ),
    db.prepare(`${counted(period)} SELECT COUNT(*) AS n FROM counted`),
  ]);

  let place = 0;
  let last: number | null = null;
  const standings = (rows.results as Row[]).map((r, i) => {
    const v = num(r.value);
    if (v !== last) place = i + 1;
    last = v;
    return {
      rank: place,
      user: linkedUser(r)!,
      value: v,
      matches: num(r.matches),
      kills: num(r.kills),
      deaths: num(r.deaths),
      wins: num(r.wins),
      finished: num(r.finished),
      best_match: r.best_id ? { id: r.best_id as string, map_title: (r.best_map as string) ?? null } : null,
    };
  });
  return { standings, matches: num((total.results[0] as Row | undefined)?.n) };
}

/** The podium's career rings: each account's newest matches, oldest first. */
export async function podiumSpokes(
  db: Db,
  users: string[],
): Promise<Record<string, Pick<RecordMatch, "id" | "kills" | "deaths" | "outcome">[]>> {
  const spokes: Record<string, Pick<RecordMatch, "id" | "kills" | "deaths" | "outcome">[]> = {};
  if (users.length === 0) return spokes;
  const slots = users.map((_, i) => `?${i + 1}`).join(", ");
  const rows = await db
    .prepare(
      `SELECT user_id, id, kills, deaths, outcome FROM (
         SELECT p.user_id, m.id, p.kills, p.deaths, p.outcome, m.ended_at,
                ROW_NUMBER() OVER (PARTITION BY p.user_id ORDER BY m.ended_at DESC) AS newest
         FROM match_players p JOIN matches m ON m.id = p.match_id
         WHERE p.user_id IN (${slots}) AND (p.kills > 0 OR p.deaths > 0)
       )
       WHERE newest <= ${PODIUM_SPOKES}
       ORDER BY ended_at`,
    )
    .bind(...users)
    .all();
  for (const r of rows.results as Row[]) {
    (spokes[r.user_id as string] ??= []).push({
      id: r.id as string,
      kills: num(r.kills),
      deaths: num(r.deaths),
      outcome: (r.outcome as RecordMatch["outcome"]) ?? null,
    });
  }
  return spokes;
}
