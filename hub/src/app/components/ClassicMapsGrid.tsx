"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowRight } from "lucide-react";

export interface RosterMap {
  name: string;
  slug: string;
  code: string | null;
  coverUrl: string | null;
  modes: string[];
  group: "halo1" | "halo2" | "community";
}

type Filter = "all" | "halo1" | "halo2" | "community";

/**
 * Visual, filterable multiplayer map roster for /multiplayer.
 * Renders crisp cover cards when D1 catalog data is present, or compact
 * tactical tiles backed by CLASSIC_MAPS when running offline.
 */
export function ClassicMapsGrid({ maps }: { maps: RosterMap[] }) {
  const [filter, setFilter] = useState<Filter>("all");
  const hasHalo2 = maps.some((m) => m.group === "halo2");
  const hasCommunity = maps.some((m) => m.group === "community");
  const showTabs = hasHalo2 || hasCommunity;

  const visible = filter === "all" ? maps : maps.filter((m) => m.group === filter);

  const tabs: { key: Filter; label: string; count: number }[] = [
    { key: "all", label: "All maps", count: maps.length },
    { key: "halo1", label: "Halo CE", count: maps.filter((m) => m.group === "halo1").length },
    ...(hasHalo2 ? [{ key: "halo2" as const, label: "Halo 2", count: maps.filter((m) => m.group === "halo2").length }] : []),
    ...(hasCommunity ? [{ key: "community" as const, label: "Community", count: maps.filter((m) => m.group === "community").length }] : []),
  ];

  return (
    <div className="mt-8">
      {showTabs && (
        <div role="tablist" aria-label="Map collection filter" className="mb-6 flex flex-wrap gap-2">
          {tabs.map((tab) => {
            const active = filter === tab.key;
            return (
              <button
                key={tab.key}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => setFilter(tab.key)}
                className={`inline-flex items-center gap-2 rounded-lg border px-3.5 py-2 text-xs font-semibold transition-all cursor-pointer ${
                  active
                    ? "border-gold/60 bg-gold/12 text-gold"
                    : "border-border bg-surface text-text-muted hover:border-border-bright hover:text-foreground"
                }`}
              >
                <span>{tab.label}</span>
                <span className="font-mono text-[10px] opacity-80">{tab.count}</span>
              </button>
            );
          })}
        </div>
      )}

      <ul
        key={filter}
        className="mj-tab-fade grid grid-cols-1 gap-3.5 sm:grid-cols-2 lg:grid-cols-3"
      >
        {visible.map((map) => (
          <li key={map.slug}>
            <Link
              href={`/mods/${map.slug}`}
              className="group card-lift flex items-center gap-3.5 overflow-hidden rounded-xl border border-border bg-surface p-2.5 transition-colors hover:border-gold/45"
            >
              <div className="relative h-16 w-24 shrink-0 overflow-hidden rounded-lg border border-border bg-surface-raised">
                {map.coverUrl ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={map.coverUrl}
                    alt=""
                    loading="lazy"
                    className="size-full object-cover transition-transform duration-500 group-hover:scale-105 motion-reduce:transition-none"
                  />
                ) : (
                  <div className="flex size-full items-center justify-center bg-[radial-gradient(ellipse_at_30%_20%,#d4a84322,transparent_60%),linear-gradient(135deg,#1a2332,#0d1117)]">
                    <span className="font-mono text-xs font-bold tracking-[0.2em] text-gold/70">
                      {map.code ?? "CE"}
                    </span>
                  </div>
                )}
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="truncate text-sm font-bold text-foreground transition-colors group-hover:text-gold">
                    {map.name}
                  </span>
                  {map.code && (
                    <span className="rounded bg-surface-raised px-1.5 py-0.5 font-mono text-[10px] text-text-dim">
                      {map.code}
                    </span>
                  )}
                </div>
                {map.modes.length > 0 && (
                  <p className="mt-1 truncate text-xs text-text-muted">{map.modes.slice(0, 3).join(" · ")}</p>
                )}
              </div>
              <ArrowRight
                aria-hidden="true"
                className="mr-1.5 size-4 shrink-0 text-text-dim transition-transform group-hover:translate-x-0.5 group-hover:text-gold"
              />
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
