"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type CSSProperties, type ReactNode } from "react";

import { GAME_TYPE_NAMES } from "@/kit/types";
import type { RecordMatch } from "@/lib/api/player-record";
import { sqlDate } from "../../matches/_components/format";
import { BASE, C, IN, OUT, SIZE, point, ringScale, spokeEnds } from "./ring";

function resultWord(m: RecordMatch) {
  if (m.outcome === "win") return "Win";
  if (m.outcome === "loss") return "Loss";
  if (m.outcome === "draw") return "Draw";
  return "Unfinished";
}

/**
 * The career signature: every match a spoke around the ring, oldest at the
 * top and clockwise to the newest. Kills reach out, deaths reach in, wins
 * are gold. No two careers draw the same one.
 *
 * Decorative to a screen reader beyond its summary: the same matches are
 * listed as links further down the page.
 */
export function CareerRing({ matches, center, summary }: { matches: RecordMatch[]; center: ReactNode; summary: string }) {
  const router = useRouter();
  const [active, setActive] = useState<number | null>(null);
  const n = matches.length;
  const scale = ringScale(matches);
  const { step, peakKills, peakDeaths, width } = scale;
  const hover = active === null ? null : matches[active];

  return (
    <figure className="mx-auto w-full max-w-[560px]">
      <div className="relative">
        <span aria-hidden className="record-ripple" />
        <svg viewBox={`0 0 ${SIZE} ${SIZE}`} className="record-ring block w-full" role="img" aria-label={summary}>
          <circle cx={C} cy={C} r={BASE + OUT} fill="none" className="stroke-gold/15" strokeDasharray="1 7" strokeLinecap="round" strokeWidth={1.5} />
          <circle cx={C} cy={C} r={BASE} fill="none" className="stroke-border-bright" strokeWidth={1} />
          <circle cx={C} cy={C} r={BASE - IN} fill="none" className="stroke-accent-red/15" strokeDasharray="1 7" strokeLinecap="round" strokeWidth={1.5} />
          {matches.map((m, i) => {
            const { kills: k, deaths: d } = spokeEnds(m, i, scale);
            const dim = active !== null && active !== i;
            const delay = { "--spoke": `${Math.round((i / n) * 900)}ms` } as CSSProperties;
            return (
              <g key={m.id} opacity={dim ? 0.3 : 1} style={delay}>
                <line
                  x1={k[0]} y1={k[1]} x2={k[2]} y2={k[3]} pathLength={1}
                  className={`record-spoke ${m.outcome === "win" ? "stroke-gold" : "stroke-silver/55"}`}
                  strokeWidth={width} strokeLinecap="round"
                />
                <line
                  x1={d[0]} y1={d[1]} x2={d[2]} y2={d[3]} pathLength={1}
                  className="record-spoke stroke-accent-red/70"
                  strokeWidth={width} strokeLinecap="round"
                />
              </g>
            );
          })}
          {/* Hit targets: a wedge per match, far wider than its spoke. */}
          {matches.map((m, i) => {
            const a = i * step;
            const [ax, ay] = point(a, BASE - IN - 6);
            const [bx, by] = point(a, BASE + OUT + 12);
            const [cx, cy] = point(a + step, BASE + OUT + 12);
            const [dx, dy] = point(a + step, BASE - IN - 6);
            return (
              <polygon
                key={m.id}
                points={`${ax},${ay} ${bx},${by} ${cx},${cy} ${dx},${dy}`}
                fill="transparent"
                className="cursor-pointer"
                onPointerEnter={() => setActive(i)}
                onPointerLeave={() => setActive((v) => (v === i ? null : v))}
                onClick={() => router.push(`/matches/${m.id}`)}
              />
            );
          })}
          {/* Where the career starts, so the clockwise reading has a beginning. */}
          <path d={`M ${C} ${C - BASE - OUT - 18} l -5 -9 h 10 z`} className="fill-gold" />
        </svg>

        <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
          <div className="flex w-[34%] flex-col items-center text-center">
            {hover ? (
              <>
                <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-gold">{resultWord(hover)}</span>
                <span className="record-display mt-1 text-4xl leading-none text-foreground tabular-nums">
                  {hover.kills}<span className="text-text-dim"> – </span>{hover.deaths}
                </span>
                <span className="mt-1.5 text-xs leading-tight text-foreground/90">{hover.map_title ?? hover.map_code}</span>
                <span className="text-[11px] text-text-muted">
                  {GAME_TYPE_NAMES[hover.game_type] ?? hover.game_type}
                  {" · "}
                  {sqlDate(hover.ended_at)?.toLocaleDateString(undefined, { month: "short", day: "numeric" })}
                </span>
              </>
            ) : (
              center
            )}
          </div>
        </div>
      </div>

      <figcaption className="relative mt-1 flex flex-wrap items-center justify-center gap-x-5 gap-y-1 text-xs text-text-muted">
        <span className="flex items-center gap-1.5"><span className="h-3 w-[3px] rounded-full bg-gold" /> Kills in a win</span>
        <span className="flex items-center gap-1.5"><span className="h-3 w-[3px] rounded-full bg-silver/55" /> Kills otherwise</span>
        <span className="flex items-center gap-1.5"><span className="h-3 w-[3px] rounded-full bg-accent-red/70" /> Deaths, inward</span>
      </figcaption>
      <p className="relative mt-1 text-center text-[11px] text-text-dim">
        {n} match{n === 1 ? "" : "es"} clockwise from the marker. Outer ring {peakKills} kill{peakKills === 1 ? "" : "s"}, inner ring {peakDeaths} death{peakDeaths === 1 ? "" : "s"}.{" "}
        <Link href="#matches" className="underline decoration-border-bright underline-offset-2 hover:text-foreground">List</Link>
      </p>
    </figure>
  );
}
