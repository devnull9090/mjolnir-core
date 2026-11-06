/**
 * The query-string filters the games, match and map pages share: which game
 * types there are, how a map code is checked, and how a filtered URL is
 * built so every link keeps the other filters.
 */
import { GAME_TYPE_NAMES, MAP_MODES } from "@/kit/types";

export const GAME_MODES = [
  "all",
  "slayer",
  "team_slayer",
  "ctf",
  "koth",
  "crazy_king",
  "team_koth",
  "oddball",
  "team_oddball",
  "juggernaut",
  "stalker",
  "reverse_tag",
  "race",
  "team_race",
  "rally",
  "team_rally",
  "forge",
] as const;
export type GameMode = (typeof GAME_MODES)[number];

/** The map page's choices: games carry variant ids, maps list engines. */
export const MAP_FILTER_MODES = ["all", ...MAP_MODES] as const;

export function parseMode(v: string | undefined): GameMode {
  return GAME_MODES.find((m) => m === v) ?? "all";
}

export function parseMapCode(v: string | undefined): string | undefined {
  return /^[A-Z0-9]{3}$/.test(v ?? "") ? v : undefined;
}

export function modeLabel(m: GameMode): string {
  return m === "all" ? "All modes" : (GAME_TYPE_NAMES[m] ?? m);
}

/**
 * `base` with `params` as its query; empty values and "all" are left out,
 * so the unfiltered page is the bare path.
 */
export function withQuery(base: string, params: Record<string, string | undefined>): string {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v && v !== "all") u.set(k, v);
  const s = u.toString();
  return s ? `${base}?${s}` : base;
}
