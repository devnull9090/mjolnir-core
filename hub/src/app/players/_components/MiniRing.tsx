import type { CSSProperties, ReactNode } from "react";

import type { RecordMatch } from "@/lib/api/player-record";
import { BASE, C, SIZE, ringScale, spokeEnds } from "./ring";

/** A career signature at podium size: just the shape, around whatever `center` is. */
export function MiniRing({
  matches,
  center,
}: {
  matches: Pick<RecordMatch, "id" | "kills" | "deaths" | "outcome">[];
  center: ReactNode;
}) {
  const scale = ringScale(matches, 14);
  return (
    <div className="relative">
      <svg viewBox={`0 0 ${SIZE} ${SIZE}`} aria-hidden className="block w-full">
        <circle cx={C} cy={C} r={BASE} fill="none" className="stroke-border-bright" strokeWidth={2} />
        {matches.map((m, i) => {
          const { kills: k, deaths: d } = spokeEnds(m, i, scale);
          const delay = { "--spoke": `${Math.round((i / matches.length) * 700)}ms` } as CSSProperties;
          return (
            <g key={m.id} style={delay}>
              <line
                x1={k[0]} y1={k[1]} x2={k[2]} y2={k[3]} pathLength={1}
                className={`record-spoke ${m.outcome === "win" ? "stroke-gold" : "stroke-silver/55"}`}
                strokeWidth={scale.width} strokeLinecap="round"
              />
              <line
                x1={d[0]} y1={d[1]} x2={d[2]} y2={d[3]} pathLength={1}
                className="record-spoke stroke-accent-red/70"
                strokeWidth={scale.width} strokeLinecap="round"
              />
            </g>
          );
        })}
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">{center}</div>
    </div>
  );
}
