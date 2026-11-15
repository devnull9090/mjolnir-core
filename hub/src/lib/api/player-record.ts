/**
 * A player's whole record: everything the player and profile pages draw
 * beyond the plain totals. Read straight from the match tables on each
 * view (a rollup table is the next step if a career ever outgrows that).
 *
 * Reports are the host's word, and a name is not an identity: see
 * docs/match_stats.md. Nothing here ranks anyone.
 */
import { linkedUser, type Db, type Row } from "./matches";

/** The career ring and the form line draw at most this many matches, newest kept. */
export const RECORD_MATCHES = 200;
/** Marks on the career map, newest kept: a dot field stays readable and light. */
const MAP_MARKS = 600;

/**
 * The incidents counted as medals. Every kill also raises a run of sibling
 * incidents (`sniper_kill`, `precision_comm`, ...), so this says what counts
 * rather than what to leave out. The whole catalogue is
 * native/lobby/medals_core.h (docs/re/medals.md).
 */
export const MEDAL_TYPES = [
  "first_blood",
  "multikill_x2",
  "multikill_x3",
  "multikill_x4",
  "multikill_x5",
  "5_in_a_row",
  "10_in_a_row",
  "15_in_a_row",
  "20_in_a_row",
  "headshot_kill",
  "sniper_headshot_kill",
  "sniper_5x",
  "sniper_10x",
  "shotgun_5x",
  "shotgun_10x",
  "splatter_5x",
  "melee_kill",
  "assassination_kill",
  "splatter_kill",
  "sticky_grenade_kill",
  "supercombine_kill",
  "sprinting_kill",
  "killjoy",
  "revenge_kill",
  "opportunist_kill",
  "avenger",
  "lifesaver",
  "kill_from_the_grave",
  "close_call",
  "highjack",
  "skyjack",
  "flagcarrier_kill",
  "extermination",
  "perfection",
  "highjack",
] as const;

export type PlayerSeatKey = { name: string } | { user: string };

export interface RecordMatch {
  id: string;
  map_code: string;
  map_title: string | null;
  game_type: string;
  ended_at: string;
  kills: number;
  deaths: number;
  place: number;
  outcome: "win" | "loss" | "draw" | null;
}

export interface RecordWeapon {
  weapon: string;
  kills: number;
  headshots: number;
}

export interface RecordRival {
  name: string;
  user: { id: string; name: string; avatar_url: string | null } | null;
  /** Kills on them, and theirs on this player. */
  kills: number;
  deaths: number;
}

export interface RecordMap {
  code: string;
  title: string | null;
  matches: number;
  kills: number;
  deaths: number;
  wins: number;
}

export interface RecordMark {
  kind: "kill" | "death";
  x: number;
  y: number;
  z: number;
  /** The victim of a kill, the killer of a death. */
  other: string | null;
  weapon: string | null;
  headshot: boolean;
}

export interface PlayerRecord {
  time_played_ms: number;
  first_played: string | null;
  assists: number;
  /** Oldest first: the newest RECORD_MATCHES the player fought in. */
  matches: RecordMatch[];
  /** How many matches the player fought in, all told. */
  fought: number;
  medals: Record<string, number>;
  weapons: RecordWeapon[];
  rivals: RecordRival[];
  maps: RecordMap[];
}

const num = (v: unknown) => (typeof v === "number" ? v : 0);

/** The seats a record covers, as a CTE and as a bare condition on match_players. */
function seats(who: PlayerSeatKey) {
  const where = "name" in who ? `name = ?1 COLLATE NOCASE` : `user_id = ?1`;
  return {
    key: "name" in who ? who.name : who.user,
    cte: `WITH seat AS (SELECT match_id, player_index FROM match_players WHERE ${where})`,
    where,
  };
}

/**
 * Medals the game sends together with another that stands for them: every
 * recorded sniper headshot also arrived as a plain headshot (172 matches,
 * 2026-11-10). The game's own HUD shows only the one; so does the case. A
 * medal is left out when its player earned one of these within HIDDEN_MS.
 */
export const MEDAL_HIDDEN_BY: Record<string, string[]> = {
  headshot_kill: ["sniper_headshot_kill"],
  melee_kill: ["assassination_kill", "kill_with_flag", "kill_with_oddball"],
};
const HIDDEN_MS = 500;

function hiddenClause(): string {
  const pairs = Object.entries(MEDAL_HIDDEN_BY)
    .map(([type, by]) => `(e.type = '${type}' AND h.type IN (${by.map((t) => `'${t}'`).join(", ")}))`)
    .join(" OR ");
  return `NOT EXISTS (
         SELECT 1 FROM match_events h
         WHERE h.match_id = e.match_id AND h.cause = e.cause
           AND abs(h.t_ms - e.t_ms) <= ${HIDDEN_MS} AND (${pairs}))`;
}

export async function playerRecord(db: Db, who: PlayerSeatKey): Promise<PlayerRecord> {
  const { key, cte, where } = seats(who);
  const medalList = MEDAL_TYPES.map((t) => `'${t}'`).join(", ");
  const [span, recent, medals, weapons, rivals, maps] = await db.batch([
    db.prepare(
      `SELECT SUM(m.duration_ms) AS played, MIN(m.ended_at) AS first_played,
              SUM(p.kills > 0 OR p.deaths > 0) AS fought
       FROM match_players p JOIN matches m ON m.id = p.match_id
       WHERE p.${where}`,
    ).bind(key),
    db.prepare(
      `SELECT m.id, m.map_code, ml.title AS map_title, m.game_type, m.ended_at,
              p.kills, p.deaths, p.place, p.outcome
       FROM match_players p
       JOIN matches m ON m.id = p.match_id
       LEFT JOIN map_listings ml ON ml.code = m.map_code
       WHERE p.${where} AND (p.kills > 0 OR p.deaths > 0)
       ORDER BY m.ended_at DESC LIMIT ${RECORD_MATCHES}`,
    ).bind(key),
    db.prepare(
      `${cte}
       SELECT e.type, COUNT(*) AS n
       FROM seat s
       JOIN match_events e ON e.match_id = s.match_id AND e.cause = s.player_index
       WHERE e.type IN (${medalList}, 'assist') AND ${hiddenClause()}
       GROUP BY e.type`,
    ).bind(key),
    db.prepare(
      `${cte}
       SELECT e.weapon, COUNT(*) AS kills, SUM(e.modifier = 1) AS headshots
       FROM seat s
       JOIN match_events e ON e.match_id = s.match_id AND e.cause = s.player_index
       WHERE e.type = 'kill' AND e.effect <> s.player_index AND e.weapon IS NOT NULL
       GROUP BY e.weapon ORDER BY kills DESC LIMIT 12`,
    ).bind(key),
    // Everyone this player traded kills with, one row a person: by account
    // when the seat is linked, by name when it is not.
    db.prepare(
      `${cte},
       traded AS (
         SELECT e.match_id, e.effect AS rival, 1 AS mine, 0 AS theirs
         FROM seat s JOIN match_events e ON e.match_id = s.match_id AND e.cause = s.player_index
         WHERE e.type = 'kill' AND e.effect >= 0 AND e.effect <> s.player_index
         UNION ALL
         SELECT e.match_id, e.cause, 0, 1
         FROM seat s JOIN match_events e ON e.match_id = s.match_id AND e.effect = s.player_index
         WHERE e.type = 'kill' AND e.cause >= 0 AND e.cause <> s.player_index
       )
       SELECT MAX(r.name) AS name, SUM(t.mine) AS kills, SUM(t.theirs) AS deaths,
              u.id AS u_id, u.display_name AS u_display_name, u.discord_username AS u_username,
              u.discord_id AS u_discord_id, u.discord_avatar AS u_avatar
       FROM traded t
       JOIN match_players r ON r.match_id = t.match_id AND r.player_index = t.rival
       LEFT JOIN users u ON u.id = r.user_id AND u.banned_at IS NULL
       GROUP BY COALESCE(u.id, r.name COLLATE NOCASE)
       ORDER BY SUM(t.mine) + SUM(t.theirs) DESC LIMIT 6`,
    ).bind(key),
    db.prepare(
      `SELECT m.map_code AS code, ml.title, COUNT(*) AS matches,
              SUM(p.kills) AS kills, SUM(p.deaths) AS deaths, SUM(p.outcome = 'win') AS wins
       FROM match_players p
       JOIN matches m ON m.id = p.match_id
       LEFT JOIN map_listings ml ON ml.code = m.map_code
       WHERE p.${where} AND (p.kills > 0 OR p.deaths > 0)
       GROUP BY m.map_code
       ORDER BY SUM(p.kills) + SUM(p.deaths) DESC, matches DESC`,
    ).bind(key),
  ]);

  const s = (span.results[0] ?? {}) as Row;
  const counts: Record<string, number> = {};
  for (const r of medals.results as Row[]) counts[r.type as string] = num(r.n);
  const { assist = 0, ...medalCounts } = counts;

  return {
    time_played_ms: num(s.played),
    first_played: (s.first_played as string) ?? null,
    assists: assist,
    fought: num(s.fought),
    matches: (recent.results as Row[])
      .map((r) => ({
        id: r.id as string,
        map_code: r.map_code as string,
        map_title: (r.map_title as string) ?? null,
        game_type: r.game_type as string,
        ended_at: r.ended_at as string,
        kills: num(r.kills),
        deaths: num(r.deaths),
        place: num(r.place),
        outcome: (r.outcome as RecordMatch["outcome"]) ?? null,
      }))
      .reverse(),
    medals: medalCounts,
    weapons: (weapons.results as Row[]).map((w) => ({
      weapon: w.weapon as string,
      kills: num(w.kills),
      headshots: num(w.headshots),
    })),
    rivals: (rivals.results as Row[]).map((r) => ({
      name: r.name as string,
      user: linkedUser(r),
      kills: num(r.kills),
      deaths: num(r.deaths),
    })),
    maps: (maps.results as Row[]).map((m) => ({
      code: m.code as string,
      title: (m.title as string) ?? null,
      matches: num(m.matches),
      kills: num(m.kills),
      deaths: num(m.deaths),
      wins: num(m.wins),
    })),
  };
}

/** Where this player's kills and deaths happened on one map, newest kept. */
export async function playerMapMarks(db: Db, who: PlayerSeatKey, map: string): Promise<RecordMark[]> {
  const { key, cte } = seats(who);
  const rows = await db
    .prepare(
      `${cte}
       SELECT 'kill' AS kind, e.cause_x AS x, e.cause_y AS y, e.cause_z AS z,
              o.name AS other, e.weapon, e.modifier, m.ended_at
       FROM seat s
       JOIN matches m ON m.id = s.match_id AND m.map_code = ?2
       JOIN match_events e ON e.match_id = s.match_id AND e.cause = s.player_index
       LEFT JOIN match_players o ON o.match_id = e.match_id AND o.player_index = e.effect
       WHERE e.type = 'kill' AND e.effect <> s.player_index AND e.cause_x IS NOT NULL
       UNION ALL
       SELECT 'death', e.effect_x, e.effect_y, e.effect_z, o.name, e.weapon, e.modifier, m.ended_at
       FROM seat s
       JOIN matches m ON m.id = s.match_id AND m.map_code = ?2
       JOIN match_events e ON e.match_id = s.match_id AND e.effect = s.player_index
       LEFT JOIN match_players o ON o.match_id = e.match_id AND o.player_index = e.cause
       WHERE e.type = 'kill' AND e.cause <> s.player_index AND e.effect_x IS NOT NULL
       ORDER BY 8 DESC LIMIT ${MAP_MARKS}`,
    )
    .bind(key, map)
    .all();
  return (rows.results as Row[]).map((r) => ({
    kind: r.kind as "kill" | "death",
    x: r.x as number,
    y: r.y as number,
    z: r.z as number,
    other: (r.other as string) ?? null,
    weapon: (r.weapon as string) ?? null,
    headshot: r.modifier === 1,
  }));
}

/**
 * The hub account behind a name, when every linked seat under it is the same
 * account. Two accounts on one name say nothing about who this page is.
 */
export async function nameAccount(db: Db, name: string): Promise<RecordRival["user"]> {
  const rows = await db
    .prepare(
      `SELECT DISTINCT u.id AS u_id, u.display_name AS u_display_name, u.discord_username AS u_username,
              u.discord_id AS u_discord_id, u.discord_avatar AS u_avatar
       FROM match_players p JOIN users u ON u.id = p.user_id AND u.banned_at IS NULL
       WHERE p.name = ?1 COLLATE NOCASE LIMIT 2`,
    )
    .bind(name)
    .all();
  return rows.results.length === 1 ? linkedUser(rows.results[0] as Row) : null;
}
