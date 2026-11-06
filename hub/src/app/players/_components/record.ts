/**
 * What a record says beyond its raw counts: how a player fights, their best
 * nights, and the words for each medal. Plain functions, shared by the
 * server-drawn sections and the client charts.
 */
import type { LucideIcon } from "lucide-react";
import {
  Bomb,
  Car,
  Crosshair,
  Droplet,
  Ghost,
  Hand,
  HeartPulse,
  Plane,
  Repeat,
  Shield,
  Target,
  Wind,
  Zap,
} from "lucide-react";

import type { PlayerRecord, RecordMatch, RecordWeapon } from "@/lib/api/player-record";

export type WeaponClass = "precision" | "automatic" | "close" | "explosive" | "vehicle";

/**
 * Colour follows the class, never its rank, so a player's bar and the next
 * player's read the same. Validated together on the dark surface.
 */
export const WEAPON_CLASSES: Record<WeaponClass, { label: string; colour: string; title: string }> = {
  precision: { label: "Precision", colour: "#b98c28", title: "Marksman" },
  automatic: { label: "Automatic", colour: "#4a95ea", title: "Rifleman" },
  close: { label: "Close quarters", colour: "#d96750", title: "Brawler" },
  explosive: { label: "Explosive", colour: "#9379e0", title: "Demolitions" },
  vehicle: { label: "Vehicle", colour: "#35a56e", title: "Pilot" },
};

const CLASS_ORDER: WeaponClass[] = ["precision", "automatic", "close", "explosive", "vehicle"];

const CLASS_OF: Record<string, WeaponClass> = {
  SniperRifle: "precision",
  MagnumPistol: "precision",
  MarksmanRifle: "precision",
  AssaultRifle: "automatic",
  Smg: "automatic",
  PlasmaRifle: "automatic",
  Needler: "automatic",
  Shotgun: "close",
  Melee: "close",
  EnergyBlade: "close",
  FragGrenade: "explosive",
  PlasmaGrenade: "explosive",
  RocketLauncher: "explosive",
  FlakCannon: "explosive",
  Explosion: "explosive",
  Ghost: "vehicle",
  Banshee: "vehicle",
  BansheeBomb: "vehicle",
  WarthogDriver: "vehicle",
  Scorpion: "vehicle",
  CollisionDamage: "vehicle",
};

/** Kills under this say too little about how someone plays. */
const STYLE_MIN_KILLS = 15;
/** A class needs this share of the kills to name the player. */
const STYLE_MIN_SHARE = 0.4;

export interface StyleShare {
  key: WeaponClass;
  kills: number;
  share: number;
}

/** Kills by class of weapon, in the classes' fixed order, skipping the empty. */
export function styleShares(weapons: RecordWeapon[]): StyleShare[] {
  const kills = new Map<WeaponClass, number>();
  for (const w of weapons) {
    const c = CLASS_OF[w.weapon];
    if (c) kills.set(c, (kills.get(c) ?? 0) + w.kills);
  }
  const total = [...kills.values()].reduce((a, b) => a + b, 0);
  return CLASS_ORDER.flatMap((key) => {
    const n = kills.get(key) ?? 0;
    return n > 0 ? [{ key, kills: n, share: n / total }] : [];
  });
}

/** A title from how they get their kills, or null for too few to tell. */
export function styleTitle(shares: StyleShare[]): string | null {
  const total = shares.reduce((a, s) => a + s.kills, 0);
  if (total < STYLE_MIN_KILLS) return null;
  const top = [...shares].sort((a, b) => b.share - a.share)[0];
  return top.share >= STYLE_MIN_SHARE ? WEAPON_CLASSES[top.key].title : "All-rounder";
}

export function playedTime(ms: number): string {
  const minutes = Math.round(ms / 60000);
  const h = Math.floor(minutes / 60);
  return h > 0 ? `${h}h ${minutes % 60}m` : `${minutes}m`;
}

export function winRate(wins: number, losses: number, draws: number): string {
  const decided = wins + losses + draws;
  return decided === 0 ? "–" : `${Math.round((wins / decided) * 100)}%`;
}

export interface Bests {
  mostKills: RecordMatch | null;
  bestRatio: RecordMatch | null;
  winStreak: number;
}

/** A match needs this many kills for its ratio to count as a best. */
const RATIO_MIN_KILLS = 5;

export function personalBests(matches: RecordMatch[]): Bests {
  let mostKills: RecordMatch | null = null;
  let bestRatio: RecordMatch | null = null;
  let run = 0;
  let winStreak = 0;
  const ratio = (m: RecordMatch) => m.kills / Math.max(m.deaths, 1);
  for (const m of matches) {
    if (m.kills > 0 && (!mostKills || m.kills >= mostKills.kills)) mostKills = m;
    if (m.kills >= RATIO_MIN_KILLS && (!bestRatio || ratio(m) >= ratio(bestRatio))) bestRatio = m;
    // An abandoned match has no outcome: it neither extends a run nor ends it.
    if (m.outcome === "win") winStreak = Math.max(winStreak, ++run);
    else if (m.outcome) run = 0;
  }
  return { mostKills, bestRatio, winStreak };
}

/** K/D after each match, career to date: the form line's series. */
export function runningRatio(matches: RecordMatch[]): number[] {
  let kills = 0;
  let deaths = 0;
  return matches.map((m) => {
    kills += m.kills;
    deaths += m.deaths;
    return kills / Math.max(deaths, 1);
  });
}

export type MedalTier = "bronze" | "silver" | "gold";

export interface MedalInfo {
  type: string;
  name: string;
  what: string;
  tier: MedalTier;
  icon?: LucideIcon;
  /** Numerals instead of an icon: the count is the point of the medal. */
  mark?: string;
}

/** Display order: the case reads from the everyday to the rare. */
export const MEDALS: MedalInfo[] = [
  { type: "first_blood", name: "First blood", what: "The first kill of the match", tier: "silver", icon: Droplet },
  { type: "headshot_kill", name: "Headshot", what: "A kill to the head", tier: "bronze", icon: Crosshair },
  { type: "sniper_headshot_kill", name: "Sniper headshot", what: "A headshot through the scope", tier: "silver", icon: Target },
  { type: "revenge_kill", name: "Revenge", what: "Killed whoever killed you last", tier: "bronze", icon: Repeat },
  { type: "killjoy", name: "Killjoy", what: "Ended someone's spree", tier: "bronze", icon: Shield },
  { type: "close_call", name: "Close call", what: "A kill with next to no shield left", tier: "bronze", icon: HeartPulse },
  { type: "kill_from_the_grave", name: "From the grave", what: "A kill after your own death", tier: "silver", icon: Ghost },
  { type: "assassination_kill", name: "Assassin", what: "A kill from behind", tier: "silver", icon: Hand },
  { type: "splatter_kill", name: "Splatter", what: "Ran someone down", tier: "bronze", icon: Car },
  { type: "sticky_grenade_kill", name: "Stuck", what: "A plasma grenade, stuck on", tier: "silver", icon: Bomb },
  { type: "highjack", name: "Hijack", what: "Took a vehicle from its driver", tier: "silver", icon: Wind },
  { type: "skyjack", name: "Skyjack", what: "Took an aircraft in flight", tier: "gold", icon: Plane },
  { type: "multikill_x2", name: "Double kill", what: "Two kills in quick succession", tier: "bronze", mark: "×2" },
  { type: "multikill_x3", name: "Triple kill", what: "Three in quick succession", tier: "silver", mark: "×3" },
  { type: "multikill_x4", name: "Overkill", what: "Four in quick succession", tier: "gold", mark: "×4" },
  { type: "5_in_a_row", name: "Killing spree", what: "Five kills without dying", tier: "bronze", mark: "5" },
  { type: "10_in_a_row", name: "Killing frenzy", what: "Ten kills without dying", tier: "silver", mark: "10" },
  { type: "15_in_a_row", name: "Running riot", what: "Fifteen kills without dying", tier: "gold", mark: "15" },
  { type: "sniper_5x", name: "Sniper spree", what: "Five sniper kills without dying", tier: "silver", icon: Zap },
  { type: "shotgun_5x", name: "Shotgun spree", what: "Five shotgun kills without dying", tier: "silver", icon: Zap },
];

export function medalTotal(record: PlayerRecord): number {
  return MEDALS.reduce((n, m) => n + (record.medals[m.type] ?? 0), 0);
}
