"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowRight, Crosshair, Globe2, Trophy, Vote } from "lucide-react";

interface FeatureSlide {
  id: string;
  tag: string;
  title: string;
  summary: string;
  image: string;
  alt: string;
  caption: string;
  href: string;
  linkLabel: string;
  icon: typeof Crosshair;
}

const FEATURES: FeatureSlide[] = [
  {
    id: "hud-modes",
    tag: "In-Game HUD",
    title: "Classic modes & team-aware HUD",
    summary:
      "Slayer, CTF, King of the Hill, Oddball, Assault, Juggernaut, Race, and Forge — backed by a native kill feed, scoreboard, radar, and objective markers.",
    image: "/blog-images/weekly-update-2/king-on-the-hill.jpg",
    alt: "In-game King of the Hill beacon and multiplayer HUD on remastered Blood Gulch",
    caption: "Blood Gulch · King of the Hill HUD",
    href: "/maps",
    linkLabel: "Browse maps & modes",
    icon: Crosshair,
  },
  {
    id: "post-game",
    tag: "Match Flow",
    title: "Post-game scoreboard & map voting",
    summary:
      "Keep the lobby rolling after the final kill. Review Red vs. Blue standings and vote on the next map and variant right inside Campaign Evolved.",
    image: "/blog-images/weekly-update-1/post-game-vote.jpg",
    alt: "Post-game Red vs Blue scoreboard and next-map voting screen inside Halo Campaign Evolved",
    caption: "In-game post-match standings & map vote",
    href: "/games",
    linkLabel: "See live lobbies",
    icon: Vote,
  },
  {
    id: "records",
    tag: "Hub Telemetry",
    title: "Combat records & 3D kill replays",
    summary:
      "Public matches report directly to the hub with full scoreboards, career rings, leaderboards, medals, and interactive 3D kill maps.",
    image: "/blog-images/weekly-update-2/combat-record.jpg",
    alt: "MJOLNIR hub Combat Record career ring and match history statistics",
    caption: "MJOLNIR Hub · Combat Record signature ring",
    href: "/matches",
    linkLabel: "Inspect recent matches",
    icon: Trophy,
  },
  {
    id: "crossplay",
    tag: "Crossplay",
    title: "16-player Steam & Game Pass lobbies",
    summary:
      "Up to 16 Spartans in one match across Steam and Xbox app / Game Pass. Missing a hub map your host picked? Download it in-game with no restart.",
    image: "/blog-images/weekly-update-2/assault-blood-gulch.jpg",
    alt: "Assault match on Blood Gulch with Warthog and objective marker in Halo Campaign Evolved",
    caption: "Up to 16 players · Zero-restart map sync",
    href: "/download",
    linkLabel: "Download the launcher",
    icon: Globe2,
  },
];

/**
 * Interactive tabbed preview of the real in-game multiplayer suite for /multiplayer.
 */
export function MultiplayerShowcase() {
  const [activeIndex, setActiveIndex] = useState(0);
  const current = FEATURES[activeIndex] ?? FEATURES[0];

  return (
    <div className="mt-10 grid gap-6 lg:grid-cols-[1.35fr_0.95fr] lg:items-stretch">
      {/* Main visual stage */}
      <figure className="relative flex flex-col overflow-hidden rounded-2xl border border-border-bright bg-background shadow-[0_24px_60px_-28px_rgba(0,0,0,0.92)]">
        <div className="relative aspect-[16/10] w-full flex-1 overflow-hidden bg-surface lg:aspect-auto lg:min-h-[380px]">
          {FEATURES.map((slide, idx) => {
            const isCurrent = idx === activeIndex;
            return (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                key={slide.id}
                src={slide.image}
                alt={isCurrent ? slide.alt : ""}
                loading={idx === 0 ? "eager" : "lazy"}
                className={`absolute inset-0 size-full object-cover transition-all duration-500 ease-out motion-reduce:transition-none ${
                  isCurrent ? "opacity-100 scale-100" : "pointer-events-none opacity-0 scale-[1.03]"
                }`}
              />
            );
          })}
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-0 bg-gradient-to-t from-background/90 via-background/15 to-transparent"
          />
          <div className="absolute inset-x-0 bottom-0 flex flex-wrap items-end justify-between gap-3 p-5">
            <div>
              <span className="inline-block rounded-md border border-gold/40 bg-background/80 px-2.5 py-1 font-mono text-[10px] font-semibold uppercase tracking-[0.16em] text-gold backdrop-blur-md">
                {current.tag}
              </span>
              <p className="mt-2 font-mono text-[11px] uppercase tracking-[0.14em] text-slate-200">
                {current.caption}
              </p>
            </div>
            <Link
              href={current.href}
              className="inline-flex items-center gap-1.5 rounded-lg border border-white/20 bg-background/75 px-3 py-1.5 text-xs font-semibold text-white backdrop-blur-md transition-colors hover:border-gold/60 hover:text-gold"
            >
              {current.linkLabel} <ArrowRight aria-hidden="true" className="size-3.5" />
            </Link>
          </div>
        </div>
      </figure>

      {/* Feature selector stack */}
      <div className="flex flex-col gap-3" role="tablist" aria-label="Multiplayer capabilities">
        {FEATURES.map((item, idx) => {
          const Icon = item.icon;
          const active = idx === activeIndex;
          return (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => setActiveIndex(idx)}
              className={`group relative flex flex-1 items-start gap-3.5 rounded-xl border p-4 text-left transition-all duration-200 cursor-pointer ${
                active
                  ? "border-gold/55 bg-surface-raised/90 shadow-[0_12px_30px_-18px_rgba(212,168,67,0.45)]"
                  : "border-border bg-surface/65 hover:border-border-bright hover:bg-surface"
              }`}
            >
              {active && (
                <span
                  aria-hidden="true"
                  className="absolute inset-y-3 left-0 w-[3px] rounded-r-full bg-gold"
                />
              )}
              <span
                className={`mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg border transition-colors ${
                  active
                    ? "border-gold/40 bg-gold/15 text-gold"
                    : "border-border bg-background/70 text-text-muted group-hover:text-foreground"
                }`}
              >
                <Icon aria-hidden="true" className="size-4" />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <h3
                    className={`text-sm font-bold transition-colors ${
                      active ? "text-foreground" : "text-slate-200 group-hover:text-foreground"
                    }`}
                  >
                    {item.title}
                  </h3>
                  <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-text-dim">
                    0{idx + 1}
                  </span>
                </div>
                <p className="mt-1 text-xs leading-5 text-text-muted">{item.summary}</p>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
