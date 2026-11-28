"use client";

import { useEffect, useState, type CSSProperties, type ReactNode } from "react";
import Link from "next/link";
import { ArrowRight, ArrowUpRight } from "lucide-react";

import type { HeroScene } from "@/lib/marketing";

const ROTATE_MS = 7500;

/**
 * Full-bleed hero backdrop that crossfades through classic Halo map captures
 * with an unobtrusive bottom scene scrubber. Pauses on hover, when the tab is
 * hidden, and automatically disables rotation for `prefers-reduced-motion`.
 */
export function HeroRotator({
  scenes,
  multiplayerHref,
  bottomLeft,
  children,
}: {
  scenes: HeroScene[];
  multiplayerHref?: string;
  bottomLeft?: ReactNode;
  children: ReactNode;
}) {
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    if (scenes.length <= 1 || paused) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    const timer = setInterval(() => {
      if (!document.hidden) {
        setIndex((i) => (i + 1) % scenes.length);
      }
    }, ROTATE_MS);
    return () => clearInterval(timer);
  }, [scenes.length, paused]);

  const active = scenes[index] ?? scenes[0];

  return (
    <section className="marketing-hero relative isolate overflow-hidden">
      {/* Crossfading full-bleed gameplay captures */}
      <div aria-hidden="true" className="absolute inset-0 -z-20 overflow-hidden bg-background">
        {scenes.map((scene, i) => {
          const isCurrent = i === index;
          return (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              key={`${scene.slug}-${i}`}
              src={scene.image}
              alt={isCurrent ? scene.alt : ""}
              fetchPriority={i === 0 ? "high" : undefined}
              loading={i <= 1 ? "eager" : "lazy"}
              style={{ objectPosition: scene.position ?? "center 45%" }}
              className={`absolute inset-0 size-full object-cover transition-opacity duration-1000 ease-in-out motion-reduce:transition-none ${
                isCurrent ? "opacity-100 mj-hero-drift" : "opacity-0 scale-105"
              }`}
            />
          );
        })}
      </div>

      {/* Left-weighted editorial scrim so the right side lets the map vista shine */}
      <div aria-hidden="true" className="marketing-hero-shade absolute inset-0 -z-10" />

      <div className="mx-auto flex min-h-[min(86vh,760px)] max-w-6xl flex-col justify-end px-6 pb-10 pt-40 md:pb-14 md:pt-48">
        <div>{children}</div>

        {/* Bottom editorial rail + interactive map capture switcher */}
        <div className="mj-rise mj-rise-d5 mt-16 flex flex-wrap items-center justify-between gap-x-6 gap-y-4 border-t border-white/15 pt-5">
          {bottomLeft ?? (
            multiplayerHref ? (
              <Link
                href={multiplayerHref}
                className="group inline-flex items-center gap-2.5 text-sm font-semibold text-white transition-colors hover:text-gold"
              >
                Does Campaign Evolved have multiplayer?{" "}
                <ArrowRight aria-hidden="true" className="size-4 transition-transform group-hover:translate-x-1" />
              </Link>
            ) : <span />
          )}

          {active && (
            <div
              className="flex flex-wrap items-center gap-4"
              onMouseEnter={() => setPaused(true)}
              onMouseLeave={() => setPaused(false)}
            >
              <Link
                href={active.href ?? `/mods/${active.slug}`}
                className="group inline-flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-[0.16em] text-slate-300 transition-colors hover:text-gold"
                title={`View ${active.name} on the hub`}
              >
                <span className="text-slate-400">In-game capture</span>
                <span aria-hidden="true" className="text-white/30">/</span>
                <span className="font-semibold text-white group-hover:text-gold">
                  {active.name}
                  {active.tag ? ` · ${active.tag}` : ""}
                </span>
                <ArrowUpRight aria-hidden="true" className="size-3.5 text-gold/80 transition-transform group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
              </Link>

              {scenes.length > 1 && (
                <div className="flex items-center gap-1.5" role="tablist" aria-label="Hero map captures">
                  {scenes.map((scene, i) => {
                    const isCurrent = i === index;
                    const label = scene.tag ? `${scene.name} (${scene.tag})` : scene.name;
                    return (
                      <button
                        key={`${scene.slug}-${i}`}
                        type="button"
                        role="tab"
                        aria-selected={isCurrent}
                        aria-label={`Show ${label}`}
                        title={label}
                        onClick={() => setIndex(i)}
                        className="group py-2 cursor-pointer"
                      >
                        <span
                          className={`relative block h-[3px] overflow-hidden rounded-full transition-all duration-300 ${
                            isCurrent
                              ? "w-9 bg-white/25"
                              : "w-4 bg-white/20 group-hover:w-6 group-hover:bg-white/45"
                          }`}
                        >
                          {isCurrent && (
                            <span
                              key={`${scene.slug}-${i}-${paused ? "p" : "r"}`}
                              style={{ "--scene-ms": `${ROTATE_MS}ms` } as CSSProperties}
                              className={`absolute inset-0 rounded-full bg-gold ${
                                paused ? "" : "mj-scene-progress"
                              }`}
                            />
                          )}
                        </span>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
