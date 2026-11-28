"use client";

import { useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  Blocks,
  Car,
  Crosshair,
  Crown,
  Flag,
  Shield,
  Skull,
  Swords,
  type LucideIcon,
} from "lucide-react";

interface ModeEntry {
  key: string;
  mapMode: string;
  matchMode: string;
  name: string;
  /** Compact tab label so narrow columns never truncate mid-word. */
  tabLabel?: string;
  tagline: string;
  description: string;
  format: string;
  highlight: string;
  icon: LucideIcon;
  featured?: boolean;
}

const MODES: ModeEntry[] = [
  {
    key: "slayer",
    mapMode: "slayer",
    matchMode: "slayer",
    name: "Slayer",
    tagline: "Every kill counts. First to the score limit wins.",
    description:
      "Classic free-for-all Halo combat. Learn weapon timers, hold high ground, control Overshield and Active Camo, and climb the scoreboard from first blood to game over.",
    format: "Free-for-all · Up to 16 players",
    highlight: "Core mode across all classic & community arenas",
    icon: Crosshair,
    featured: true,
  },
  {
    key: "ctf",
    mapMode: "ctf",
    matchMode: "ctf",
    name: "Capture the Flag",
    tabLabel: "CTF",
    tagline: "Defend your base. Take theirs. Bring it home.",
    description:
      "Red vs. Blue objective warfare at its purest. Coordinate Warthog runs across Blood Gulch, cut off flag carriers in tight corridors, and return your flag to score.",
    format: "Red vs. Blue · Team objective",
    highlight: "Full team-aware HUD, flag waypoints & carrier tracking",
    icon: Flag,
    featured: true,
  },
  {
    key: "team_slayer",
    mapMode: "slayer",
    matchMode: "team_slayer",
    name: "Team Slayer",
    tagline: "Fireteam coordination. Shared scoreboard.",
    description:
      "Two squads, one kill limit. Lock down power weapons together, trade out kills, and control map spawns with Red and Blue team armor and live team score bars.",
    format: "Red vs. Blue · Squad combat",
    highlight: "Team chat, team armor colors & post-match podiums",
    icon: Swords,
  },
  {
    key: "koth",
    mapMode: "koth",
    matchMode: "koth",
    name: "King of the Hill",
    tabLabel: "King of Hill",
    tagline: "Take the hill. Hold it against everyone.",
    description:
      "Fight for control of the contested zone while the clock ticks upward. Play classic stationary hills, rotating Crazy King zones, or Team King squad battles.",
    format: "FFA / Team · Zone control",
    highlight: "Live in-world hill markers & Crazy King support",
    icon: Crown,
  },
  {
    key: "oddball",
    mapMode: "oddball",
    matchMode: "oddball",
    name: "Oddball",
    tagline: "Hold the skull. Survive the hunt.",
    description:
      "Grab the Oddball to rack up seconds while every player on the map converges on your position. Melee lethal, weapons down — rely on movement or your fireteam.",
    format: "FFA / Team · Carrier survival",
    highlight: "Dedicated carrier waypoints & Team Oddball",
    icon: Skull,
  },
  {
    key: "juggernaut",
    mapMode: "slayer",
    matchMode: "juggernaut",
    name: "Juggernaut",
    tagline: "One hunter. Everyone else is prey.",
    description:
      "Take down the Juggernaut to claim the mantle and score kills while empowered. Built right into the Megalo variant system with configurable host settings.",
    format: "Asymmetric FFA · Variant mode",
    highlight: "Customizable host rules & score limits",
    icon: Shield,
  },
  {
    key: "race",
    mapMode: "race",
    matchMode: "race",
    name: "Race",
    tagline: "Full throttle through every checkpoint.",
    description:
      "Tear through nav-point circuits in Warthogs and Ghosts across big-team classics like Blood Gulch, Sidewinder, and Death Island. Includes Team Race and Rally.",
    format: "Vehicles · Checkpoint circuit",
    highlight: "Full vehicle physics & Rally variants",
    icon: Car,
  },
  {
    key: "forge",
    mapMode: "all",
    matchMode: "forge",
    name: "Forge",
    tagline: "Build arenas together, in-game.",
    description:
      "Spawn modular blocks, ramps, lights, grav-lifts, and automatic doors from community Forge packs right inside a live session — then save and share what you build.",
    format: "Creative · Modular Forge packs",
    highlight: "Supports custom community Forge packs from the hub",
    icon: Blocks,
  },
];

/**
 * Interactive tactical game mode explorer for the hub homepage.
 */
export function ModesShowcase() {
  const [selectedKey, setSelectedKey] = useState<string>("slayer");
  const active = MODES.find((m) => m.key === selectedKey) ?? MODES[0];
  const ActiveIcon = active.icon;

  return (
    <div className="space-y-4">
      {/* Compact selectable mode grid */}
      <div
        role="tablist"
        aria-label="Game modes"
        className="grid grid-cols-2 gap-2.5 sm:grid-cols-4"
      >
        {MODES.map((mode) => {
          const Icon = mode.icon;
          const isSelected = mode.key === active.key;
          return (
            <button
              key={mode.key}
              type="button"
              role="tab"
              aria-selected={isSelected}
              onClick={() => setSelectedKey(mode.key)}
              className={`group flex items-center gap-2.5 rounded-lg border px-3 py-3 text-left transition-all duration-200 cursor-pointer ${
                isSelected
                  ? "border-gold/60 bg-gold/12 text-foreground shadow-[0_8px_24px_-14px_rgba(212,168,67,0.5)]"
                  : "border-border-bright/80 bg-background/60 text-text-muted hover:border-gold/35 hover:bg-surface-raised hover:text-foreground"
              }`}
            >
              <Icon
                aria-hidden="true"
                className={`size-4 shrink-0 transition-colors ${
                  isSelected ? "text-gold" : "text-text-dim group-hover:text-gold"
                }`}
              />
              <span title={mode.name} className="truncate text-xs font-semibold sm:text-sm">
                {mode.tabLabel ?? mode.name}
              </span>
            </button>
          );
        })}
      </div>

      {/* Tactical briefing card for the active mode */}
      <div
        key={active.key}
        role="tabpanel"
        className="mj-tab-fade mj-hud-corners rounded-xl border border-border-bright bg-background/75 p-6 sm:p-7"
      >
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-start gap-4">
            <div className="flex size-12 shrink-0 items-center justify-center rounded-xl border border-gold/30 bg-gold/10 text-gold">
              <ActiveIcon aria-hidden="true" className="size-6" />
            </div>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-2xl font-black tracking-tight text-foreground">{active.name}</h3>
                {active.featured && (
                  <span className="rounded-full border border-gold/35 bg-gold/10 px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider text-gold">
                    Core mode
                  </span>
                )}
              </div>
              <p className="mt-1 text-sm font-medium text-gold">{active.tagline}</p>
            </div>
          </div>
          <span className="rounded-md border border-border bg-surface px-2.5 py-1 font-mono text-[11px] text-text-muted">
            {active.format}
          </span>
        </div>

        <p className="mt-5 text-sm leading-7 text-text-muted">{active.description}</p>

        <div className="mt-5 flex flex-wrap items-center justify-between gap-4 border-t border-border pt-4">
          <p className="font-mono text-[11px] uppercase tracking-wider text-text-dim">
            {active.highlight}
          </p>
          <div className="flex flex-wrap items-center gap-4 text-xs font-semibold">
            {active.key === "forge" ? (
              <Link href="/forge" className="inline-flex items-center gap-1.5 text-gold hover:underline">
                Browse Forge packs <ArrowRight aria-hidden="true" className="size-3.5" />
              </Link>
            ) : (
              <>
                <Link
                  href={active.mapMode === "all" ? "/maps" : `/maps?mode=${active.mapMode}`}
                  className="inline-flex items-center gap-1.5 text-gold hover:underline"
                >
                  {active.name} maps <ArrowRight aria-hidden="true" className="size-3.5" />
                </Link>
                <Link
                  href={`/matches?mode=${active.matchMode}`}
                  className="inline-flex items-center gap-1.5 text-text-muted hover:text-foreground"
                >
                  Match history <ArrowRight aria-hidden="true" className="size-3.5" />
                </Link>
              </>
            )}
          </div>
        </div>
      </div>

      <p className="text-xs leading-6 text-text-muted">
        Available modes depend on the map and installed game variant. Supports up to 16 players with live host rule customization.
      </p>
    </div>
  );
}
