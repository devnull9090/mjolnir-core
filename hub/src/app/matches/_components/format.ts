/**
 * Words for match data: durations, times, weapons and what an event says.
 * Shared by the match, player and profile pages.
 */
import type { MatchEvent, MatchPlayer, MatchSummary } from "@/lib/api/matches";

export function duration(ms: number): string {
  const s = Math.round(ms / 1000);
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, "0")}`;
}

/** "2026-10-03 21:14:05" (UTC, SQLite's format) as a Date, or null. */
export function sqlDate(sqlTime: string): Date | null {
  const d = new Date(sqlTime.replace(" ", "T") + "Z");
  return Number.isNaN(d.getTime()) ? null : d;
}

/**
 * A SQLite time as a short UTC date: what the server renders, and what
 * metadata says. Pages show <LocalTime>, which turns it local in the browser.
 */
export function when(sqlTime: string): string {
  const d = sqlDate(sqlTime);
  if (!d) return sqlTime;
  return d.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone: "UTC",
    timeZoneName: "short",
  });
}

/** "AssaultRifle" -> "Assault Rifle". */
export function weaponName(weapon: string | null): string | null {
  if (!weapon) return null;
  return weapon.replace(/_/g, " ").replace(/([a-z])([A-Z])/g, "$1 $2");
}

export function winnerText(m: Pick<MatchSummary, "winner" | "winner_name" | "end_reason">): string {
  if (m.end_reason === "abandoned") return "Abandoned";
  if (m.winner === "draw" || m.winner === null) return "Draw";
  if (m.winner === "red") return "Red team";
  if (m.winner === "blue") return "Blue team";
  return m.winner_name ?? `Player ${Number(m.winner) + 1}`;
}

/** A seat's history: the hub account's when the seat is linked, the in-game name's otherwise. */
export function playerHref(p: { name: string; user: { id: string } | null }): string {
  return p.user ? `/users/${p.user.id}` : `/players/${encodeURIComponent(p.name)}`;
}

/** The map's hub page, when its listing is published. */
export function mapHref(m: Pick<MatchSummary, "map_slug">): string | null {
  return m.map_slug ? `/mods/${m.map_slug}` : null;
}

export function kd(kills: number, deaths: number): string {
  return deaths === 0 ? kills.toFixed(2) : (kills / deaths).toFixed(2);
}

// EBlamDamageReportingModifier
const MODIFIER_VERBS: Record<number, string> = {
  1: "headshot",
  2: "assassinated",
  3: "splattered",
  4: "stuck",
  5: "assassinated",
};

const MEDALS: Record<string, string> = {
  first_blood: "First blood",
  multikill_x2: "Double kill",
  multikill_x3: "Triple kill",
  multikill_x4: "Overkill",
  "5_in_a_row": "Killing spree",
  "10_in_a_row": "Killing frenzy",
};

const FLAG_TEAMS = ["Red", "Blue"];

/**
 * One line of the timeline, or null for incidents shown only as counts
 * (commendations, lead changes, deaths a kill line already tells).
 */
export function eventLine(e: MatchEvent, nameOf: (index: number) => string): string | null {
  const cause = e.cause >= 0 ? nameOf(e.cause) : null;
  const effect = e.effect >= 0 ? nameOf(e.effect) : null;
  const flag = e.value === 0 || e.value === 1 ? FLAG_TEAMS[e.value] : "the";
  switch (e.type) {
    case "kill": {
      const weapon = weaponName(e.weapon);
      const verb = (e.modifier !== null && MODIFIER_VERBS[e.modifier]) || "killed";
      return `${cause ?? "?"} ${verb} ${effect ?? "?"}${weapon ? ` (${weapon})` : ""}`;
    }
    case "suicide":
      return `${effect ?? cause ?? "?"} committed suicide`;
    case "flag_grabbed":
      return `${cause ?? "Someone"} grabbed the ${flag} flag`;
    case "flag_scored":
      return `${cause ?? "Someone"} captured the ${flag} flag`;
    case "flag_recovered":
      return `${cause ?? "Someone"} recovered the ${flag} flag`;
    case "flag_reset":
      return `The ${flag} flag reset`;
    case "player_joined":
    case "player_rejoined":
      return `${cause ?? "A player"} joined`;
    case "player_quit":
      return `${cause ?? "A player"} quit`;
    case "player_booted_player":
      return `${effect ?? "A player"} was booted`;
    case "death":
      // Only deaths no kill or suicide tells: see explainedDeaths.
      return `${effect ?? "?"} died`;
    case "round_over":
    case "game_over":
      return "The match ended";
    default:
      return MEDALS[e.type] && cause ? `${cause}: ${MEDALS[e.type]}` : null;
  }
}

/** Seat names by index, for event lines. */
export function namer(players: Pick<MatchPlayer, "index" | "name">[]) {
  const names = new Map(players.map((p) => [p.index, p.name]));
  return (index: number) => names.get(index) ?? `Player ${index + 1}`;
}

/**
 * Deaths are raised beside the kill or suicide that caused them; a death is
 * worth its own line (or dot) only when nothing else explains it: a fall,
 * the guardians, a script. Keys are "<victim>:<second>".
 */
export function explainedDeaths(events: MatchEvent[]): Set<string> {
  const key = (e: MatchEvent) => `${e.effect}:${Math.round(e.t_ms / 1000)}`;
  return new Set(events.filter((e) => e.type === "kill" || e.type === "suicide").map(key));
}

export function isExplainedDeath(e: MatchEvent, explained: Set<string>): boolean {
  return e.type === "death" && explained.has(`${e.effect}:${Math.round(e.t_ms / 1000)}`);
}
