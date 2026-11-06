"use client";

import { useState, type PointerEvent } from "react";

import type { RecordMatch } from "@/lib/api/player-record";
import { sqlDate } from "../../matches/_components/format";

const W = 720;
const H = 240;
const PAD = { top: 16, right: 12, bottom: 22, left: 34 };

/**
 * Career K/D after each match, oldest to newest, against the even line at
 * 1.00. One series, so the title names it; hover reads any match off it.
 */
export function FormLine({ matches, ratios }: { matches: RecordMatch[]; ratios: number[] }) {
  const [at, setAt] = useState<number | null>(null);
  const n = ratios.length;
  const top = Math.max(Math.ceil(Math.max(...ratios, 1) * 2) / 2, 1.5);
  const x = (i: number) => PAD.left + (n > 1 ? (i / (n - 1)) * (W - PAD.left - PAD.right) : 0);
  const y = (v: number) => PAD.top + (1 - v / top) * (H - PAD.top - PAD.bottom);
  const line = ratios.map((v, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join(" ");
  const area = `${line} L${x(n - 1).toFixed(1)} ${y(0)} L${x(0).toFixed(1)} ${y(0)} Z`;
  const ticks = [0, 1, top].filter((v, i, all) => all.indexOf(v) === i);

  const onMove = (e: PointerEvent<SVGSVGElement>) => {
    const box = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - box.left) / box.width) * W;
    const i = Math.round(((px - PAD.left) / (W - PAD.left - PAD.right)) * (n - 1));
    setAt(Math.min(n - 1, Math.max(0, i)));
  };

  const m = at === null ? null : matches[at];
  const left = at === null ? 0 : (x(at) / W) * 100;

  return (
    <figure className="relative">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="block w-full touch-none"
        role="img"
        aria-label={`Career kills per death over ${n} matches, now ${ratios[n - 1]?.toFixed(2) ?? "0.00"}`}
        onPointerMove={onMove}
        onPointerLeave={() => setAt(null)}
      >
        <defs>
          <linearGradient id="form-fill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0" stopColor="var(--color-gold)" stopOpacity="0.22" />
            <stop offset="1" stopColor="var(--color-gold)" stopOpacity="0" />
          </linearGradient>
        </defs>
        {ticks.map((v) => (
          <g key={v}>
            <line
              x1={PAD.left} x2={W - PAD.right} y1={y(v)} y2={y(v)}
              className={v === 1 ? "stroke-text-dim" : "stroke-border"}
              strokeDasharray={v === 1 ? "3 5" : undefined} strokeWidth={1}
            />
            <text x={PAD.left - 8} y={y(v) + 4} textAnchor="end" className="fill-text-muted text-[11px] tabular-nums">
              {v.toFixed(v === 0 ? 0 : 1)}
            </text>
          </g>
        ))}
        <text x={PAD.left} y={H - 4} className="fill-text-dim text-[11px]">First match</text>
        <text x={W - PAD.right} y={H - 4} textAnchor="end" className="fill-text-dim text-[11px]">Latest</text>
        {n > 1 && <path d={area} fill="url(#form-fill)" />}
        {n > 1 && <path d={line} fill="none" className="stroke-gold" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />}
        {at !== null ? (
          <>
            <line x1={x(at)} x2={x(at)} y1={PAD.top} y2={y(0)} className="stroke-text-dim" strokeWidth={1} />
            <circle cx={x(at)} cy={y(ratios[at])} r={5} className="fill-gold stroke-surface" strokeWidth={2} />
          </>
        ) : (
          n > 0 && <circle cx={x(n - 1)} cy={y(ratios[n - 1])} r={4} className="fill-gold stroke-surface" strokeWidth={2} />
        )}
      </svg>
      {m && at !== null && (
        <div
          className="pointer-events-none absolute top-0 z-10 rounded-md border border-border-bright bg-background/95 px-2.5 py-1.5 text-xs shadow-lg"
          style={left > 60 ? { right: `${100 - left + 1.5}%` } : { left: `${left + 1.5}%` }}
        >
          <p className="font-semibold tabular-nums text-foreground">{ratios[at].toFixed(2)} career K/D</p>
          <p className="whitespace-nowrap text-text-muted">
            {m.kills}–{m.deaths} on {m.map_title ?? m.map_code}
            {" · "}
            {sqlDate(m.ended_at)?.toLocaleDateString(undefined, { month: "short", day: "numeric" })}
          </p>
        </div>
      )}
    </figure>
  );
}
