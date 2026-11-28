"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowRight, Download, Rocket, Users } from "lucide-react";

import { LAUNCHER_LINK_TITLE } from "./JoinButton";

export interface FeaturedMapItem {
  code: string;
  name: string;
  slug: string;
  image: string;
  tagline: string;
  number: string;
  gameLabel: string;
  modes: string[];
  playersLabel: string | null;
  sizeLabel: string | null;
  vehicles: boolean | null;
  downloads: number | null;
  hasRelease: boolean;
}

/**
 * Interactive battleground stage for the hub homepage.
 * Lets visitors flip through iconic classic maps with live catalog facts,
 * crossfading imagery, and direct launcher/map-page links.
 */
export function MapShowcase({ maps }: { maps: FeaturedMapItem[] }) {
  const [activeIndex, setActiveIndex] = useState(0);
  const current = maps[activeIndex] ?? maps[0];
  if (!current) return null;

  return (
    <div className="mt-10 grid gap-5 lg:grid-cols-[1.55fr_0.95fr]">
      {/* Main cinematic preview stage */}
      <div className="mj-hud-corners group relative overflow-hidden rounded-xl border border-border-bright bg-surface">
        <div className="relative aspect-[16/10] w-full overflow-hidden bg-surface-raised">
          {maps.map((map, idx) => (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              key={map.slug}
              src={map.image}
              alt={`${map.name} running in Halo Campaign Evolved with MJOLNIR`}
              loading={idx === 0 ? "eager" : "lazy"}
              className={`absolute inset-0 size-full object-cover transition-all duration-700 ease-out motion-reduce:transition-none ${
                idx === activeIndex
                  ? "opacity-100 scale-100 group-hover:scale-[1.03]"
                  : "opacity-0 scale-[1.04] pointer-events-none"
              }`}
            />
          ))}
          <div
            aria-hidden="true"
            className="absolute inset-0 bg-gradient-to-t from-background via-background/45 to-transparent"
          />

          {/* Top tactical bar */}
          <div className="absolute inset-x-4 top-4 flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <span className="rounded bg-background/85 px-2.5 py-1 font-mono text-[11px] font-bold tracking-[0.18em] text-gold backdrop-blur-md border border-gold/25">
                {current.code} / {current.number}
              </span>
              <span className="rounded bg-background/80 px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-slate-200 backdrop-blur-md border border-white/10">
                {current.gameLabel}
              </span>
            </div>
            {current.downloads !== null && current.downloads > 0 && (
              <span className="inline-flex items-center gap-1.5 rounded bg-background/80 px-2.5 py-1 font-mono text-[11px] text-slate-200 backdrop-blur-md border border-white/10 tabular-nums">
                <Download aria-hidden="true" className="size-3 text-gold" />
                {current.downloads.toLocaleString("en-US")}
              </span>
            )}
          </div>

          {/* Bottom info overlay */}
          <div key={current.slug} className="mj-tab-fade absolute inset-x-5 bottom-5 sm:inset-x-6 sm:bottom-6">
            <div className="flex flex-wrap items-center gap-1.5 mb-2.5">
              {current.modes.slice(0, 4).map((mode) => (
                <span
                  key={mode}
                  className="rounded-full border border-gold/35 bg-gold/15 px-2.5 py-0.5 text-[11px] font-semibold text-gold backdrop-blur-sm"
                >
                  {mode}
                </span>
              ))}
              {current.vehicles && (
                <span className="rounded-full border border-white/15 bg-background/70 px-2.5 py-0.5 text-[11px] font-medium text-slate-200 backdrop-blur-sm">
                  Vehicles
                </span>
              )}
            </div>
            <h3 className="text-2xl font-black tracking-tight text-white sm:text-3xl">{current.name}</h3>
            <p className="mt-1.5 max-w-xl text-sm leading-6 text-slate-300">{current.tagline}</p>

            <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-white/15 pt-4">
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[11px] uppercase tracking-wider text-slate-300">
                {current.sizeLabel && <span>{current.sizeLabel}</span>}
                {current.playersLabel && (
                  <span className="inline-flex items-center gap-1.5">
                    <Users aria-hidden="true" className="size-3.5 text-gold" />
                    {current.playersLabel}
                  </span>
                )}
              </div>
              <div className="flex flex-wrap items-center gap-3">
                {current.hasRelease && (
                  <a
                    href={`mjolnir://map/${current.code}`}
                    title={`${LAUNCHER_LINK_TITLE} on this map's page.`}
                    className="inline-flex items-center gap-1.5 rounded-md border border-gold/40 bg-gold/15 px-3 py-1.5 text-xs font-semibold text-gold backdrop-blur-sm transition-colors hover:bg-gold/25"
                  >
                    <Rocket aria-hidden="true" className="size-3.5" />
                    Open in launcher
                  </a>
                )}
                <Link
                  href={`/mods/${current.slug}`}
                  className="inline-flex items-center gap-1.5 text-xs font-semibold text-white transition-colors hover:text-gold"
                >
                  Map details <ArrowRight aria-hidden="true" className="size-3.5 text-gold" />
                </Link>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Interactive battleground selector rail */}
      <div className="flex flex-col gap-2.5" role="tablist" aria-label="Featured maps">
        {maps.map((map, idx) => {
          const active = idx === activeIndex;
          return (
            <button
              key={map.slug}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => setActiveIndex(idx)}
              className={`group relative flex flex-1 items-center gap-3.5 overflow-hidden rounded-xl border p-3 text-left transition-all duration-200 cursor-pointer ${
                active
                  ? "border-gold/55 bg-surface-card/90 shadow-[0_12px_30px_-18px_rgba(212,168,67,0.45)]"
                  : "border-border bg-surface/80 hover:border-border-bright hover:bg-surface-raised"
              }`}
            >
              {/* Left active accent rail */}
              <span
                aria-hidden="true"
                className={`absolute inset-y-2 left-0 w-1 rounded-r-full transition-all duration-200 ${
                  active ? "bg-gold opacity-100" : "bg-gold/40 opacity-0 group-hover:opacity-60"
                }`}
              />
              <div className="relative h-16 w-24 shrink-0 overflow-hidden rounded-lg border border-border bg-surface-raised">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={map.image}
                  alt=""
                  loading="lazy"
                  className={`size-full object-cover transition-transform duration-500 ${
                    active ? "scale-105" : "group-hover:scale-105"
                  }`}
                />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-gold">
                    {map.number} · {map.code}
                  </span>
                  <span className="font-mono text-[10px] text-text-dim">{map.gameLabel}</span>
                </div>
                <p className={`mt-0.5 truncate text-base font-bold transition-colors ${active ? "text-white" : "text-foreground group-hover:text-gold"}`}>
                  {map.name}
                </p>
                <p className="mt-0.5 truncate text-xs text-text-muted">{map.tagline}</p>
              </div>
              <ArrowRight
                aria-hidden="true"
                className={`size-4 shrink-0 transition-transform duration-200 ${
                  active ? "translate-x-0 text-gold" : "-translate-x-1 text-text-dim opacity-0 group-hover:translate-x-0 group-hover:opacity-100"
                }`}
              />
            </button>
          );
        })}
      </div>
    </div>
  );
}
