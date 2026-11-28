"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowRight, Map as MapIcon } from "lucide-react";

export interface RosterMap {
  name: string;
  slug: string;
  code: string | null;
  coverUrl: string | null;
  modes: string[];
  group: "halo1" | "halo2" | "community";
  /** Optional subtitle badge (e.g. "Halo PC", "Halo CE", "Halo 2", "Community"). */
  badge?: string;
}

type Filter = "all" | "halo1" | "halo2" | "community" | "pc";

/**
 * Visual, filterable multiplayer map gallery for /multiplayer.
 * Renders full-bleed 16:10 visual cards backed by D1 catalog data or the
 * curated CLASSIC_MAPS roster, plus a closing catalog tile so the 4-col grid
 * stays balanced with no orphan row.
 */
export function ClassicMapsGrid({ maps }: { maps: RosterMap[] }) {
  const [filter, setFilter] = useState<Filter>("all");
  const hasHalo2 = maps.some((m) => m.group === "halo2");
  const hasCommunity = maps.some((m) => m.group === "community");
  const hasPcTag = maps.some((m) => m.badge === "Halo PC");

  const visible =
    filter === "all"
      ? maps
      : filter === "pc"
        ? maps.filter((m) => m.badge === "Halo PC")
        : maps.filter((m) => m.group === filter);

  const tabs: { key: Filter; label: string; count: number }[] = [
    { key: "all", label: "All maps", count: maps.length },
    {
      key: "halo1",
      label: hasHalo2 || hasCommunity ? "Halo CE" : "Xbox Originals",
      count:
        hasHalo2 || hasCommunity
          ? maps.filter((m) => m.group === "halo1").length
          : maps.filter((m) => m.group === "halo1" && m.badge !== "Halo PC").length,
    },
    ...(!hasHalo2 && !hasCommunity && hasPcTag
      ? [{ key: "pc" as const, label: "Halo PC", count: maps.filter((m) => m.badge === "Halo PC").length }]
      : []),
    ...(hasHalo2 ? [{ key: "halo2" as const, label: "Halo 2", count: maps.filter((m) => m.group === "halo2").length }] : []),
    ...(hasCommunity ? [{ key: "community" as const, label: "Community", count: maps.filter((m) => m.group === "community").length }] : []),
  ];

  // When only CE maps exist offline, "Xbox Originals" excludes the 6 Halo PC maps.
  const filteredMaps =
    filter === "halo1" && !hasHalo2 && !hasCommunity && hasPcTag
      ? maps.filter((m) => m.group === "halo1" && m.badge !== "Halo PC")
      : visible;

  return (
    <div className="mt-8">
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

      <ul
        key={filter}
        className="mj-tab-fade grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4"
      >
        {filteredMaps.map((map, idx) => (
          <li key={map.slug}>
            <Link
              href={`/mods/${map.slug}`}
              className="group card-lift relative block overflow-hidden rounded-xl border border-border bg-surface transition-colors hover:border-gold/50"
            >
              <div className="relative aspect-[16/10] w-full overflow-hidden bg-[radial-gradient(ellipse_at_30%_20%,#d4a8431a,transparent_60%),linear-gradient(135deg,#18202c,#0b0f17)]">
                {map.coverUrl ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={map.coverUrl}
                    alt={`${map.name} in Halo Campaign Evolved`}
                    loading={idx < 8 ? "eager" : "lazy"}
                    decoding="async"
                    className="size-full object-cover transition-transform duration-500 ease-out group-hover:scale-[1.06] motion-reduce:transition-none"
                  />
                ) : (
                  <div className="flex size-full items-center justify-center">
                    <span className="font-mono text-sm font-bold tracking-[0.22em] text-gold/70">
                      {map.code ?? "CE"}
                    </span>
                  </div>
                )}

                <div
                  aria-hidden="true"
                  className="pointer-events-none absolute inset-0 bg-gradient-to-t from-[#06080f] via-[#06080f]/35 to-transparent"
                />

                {/* Top metadata badges */}
                <div className="absolute inset-x-2.5 top-2.5 flex items-center justify-between gap-2">
                  {map.code ? (
                    <span className="rounded border border-white/15 bg-background/75 px-1.5 py-0.5 font-mono text-[10px] font-semibold tracking-[0.14em] text-gold backdrop-blur-sm">
                      {map.code}
                    </span>
                  ) : (
                    <span />
                  )}
                  {map.badge && (
                    <span className="rounded border border-white/10 bg-background/70 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-[0.14em] text-slate-300 backdrop-blur-sm">
                      {map.badge}
                    </span>
                  )}
                </div>

                {/* Bottom title + modes overlay */}
                <div className="absolute inset-x-0 bottom-0 flex items-end justify-between gap-2 px-3 pb-2.5 pt-6">
                  <div className="min-w-0">
                    <h3 className="truncate text-sm font-bold text-white transition-colors group-hover:text-gold">
                      {map.name}
                    </h3>
                    {map.modes.length > 0 && (
                      <p className="mt-0.5 truncate text-[11px] text-slate-300/90">
                        {map.modes.slice(0, 3).join(" · ")}
                      </p>
                    )}
                  </div>
                  <ArrowRight
                    aria-hidden="true"
                    className="mb-0.5 size-3.5 shrink-0 text-slate-400 transition-transform group-hover:translate-x-0.5 group-hover:text-gold"
                  />
                </div>
              </div>
            </Link>
          </li>
        ))}

        {/* Closing catalog tile (keeps 19 CE classics + 1 CTA = clean 4×5 balanced grid) */}
        {filter === "all" && (
          <li>
            <Link
              href="/maps"
              className="group card-lift flex aspect-[16/10] flex-col justify-between rounded-xl border border-dashed border-gold/35 bg-[radial-gradient(ellipse_at_top_right,#d4a8431a,transparent_65%),var(--color-surface)] p-4 transition-colors hover:border-gold/70 hover:bg-surface-raised"
            >
              <span className="inline-flex size-8 items-center justify-center rounded-lg border border-gold/30 bg-gold/10 text-gold">
                <MapIcon aria-hidden="true" className="size-4" />
              </span>
              <div>
                <p className="text-sm font-bold text-foreground transition-colors group-hover:text-gold">
                  Browse the full map catalog
                </p>
                <p className="mt-1 inline-flex items-center gap-1.5 text-xs text-text-muted group-hover:text-gold">
                  Halo 2, Forge &amp; community maps{" "}
                  <ArrowRight aria-hidden="true" className="size-3.5 transition-transform group-hover:translate-x-0.5" />
                </p>
              </div>
            </Link>
          </li>
        )}
      </ul>
    </div>
  );
}
