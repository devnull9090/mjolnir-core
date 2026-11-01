/**
 * The query-string filters the games and match pages share: which game
 * types there are, how a map code is checked, and how a filtered URL is
 * built so every link keeps the other filters.
 */
import { GAME_TYPE_NAMES } from "@/kit/types";

export const GAME_MODES = ["all", "slayer", "ctf", "team_slayer", "koth", "oddball"] as const;
export type GameMode = (typeof GAME_MODES)[number];

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
