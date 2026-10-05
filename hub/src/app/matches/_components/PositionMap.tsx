import type { MatchEvent } from "@/lib/api/matches";
import { duration, eventLine } from "./format";

type Point = [number, number, number];

const SIZE = 560;
const PAD = 24;

/**
 * Where the kills and deaths happened, seen from above: the map's Unreal X
 * across and Y down, as the editor's top view draws it. A line joins a
 * killer (gold) to the victim (red). With `focus`, only that player's kills
 * and deaths. The first sketch of the heatmaps the positions are kept for.
 */
export function PositionMap({
  events,
  nameOf,
  focus,
}: {
  events: MatchEvent[];
  nameOf: (index: number) => string;
  focus: number | null;
}) {
  const kills = events.filter(
    (e) => e.type === "kill" && e.effect_pos && (focus === null || e.cause === focus || e.effect === focus),
  );
  // Deaths a kill doesn't account for: falls, suicides, the guardians.
  const killed = new Set(
    events.filter((e) => e.type === "kill").map((e) => `${e.effect}:${Math.round(e.t_ms / 1000)}`),
  );
  const deaths = events.filter(
    (e) =>
      e.type === "death" &&
      e.effect_pos &&
      (focus === null || e.effect === focus) &&
      !killed.has(`${e.effect}:${Math.round(e.t_ms / 1000)}`),
  );
  const points: Point[] = [
    ...kills.flatMap((e) => [e.effect_pos!, ...(e.cause_pos ? [e.cause_pos] : [])]),
    ...deaths.map((e) => e.effect_pos!),
  ];
  if (points.length === 0) {
    return <p className="text-sm text-text-muted">No positions were reported for this match.</p>;
  }
  const xs = points.map((p) => p[0]);
  const ys = points.map((p) => p[1]);
  const minX = Math.min(...xs);
  const minY = Math.min(...ys);
  // One scale for both axes, so the map keeps its shape.
  const span = Math.max(Math.max(...xs) - minX, Math.max(...ys) - minY, 1000);
  const scale = (SIZE - PAD * 2) / span;
  const at = (p: Point) => [PAD + (p[0] - minX) * scale, PAD + (p[1] - minY) * scale] as const;

  return (
    <figure>
      <svg
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        className="w-full max-w-xl rounded-xl border border-border bg-surface"
        role="img"
        aria-label="Kill and death positions, top-down"
      >
        {kills.map((e) => {
          if (!e.cause_pos || e.cause === e.effect) return null;
          const [x1, y1] = at(e.cause_pos);
          const [x2, y2] = at(e.effect_pos!);
          return (
            <line key={`l${e.seq}`} x1={x1} y1={y1} x2={x2} y2={y2} stroke="currentColor" className="text-text-dim" strokeOpacity={0.35} strokeWidth={1} />
          );
        })}
        {kills.map((e) => {
          if (!e.cause_pos || e.cause === e.effect) return null;
          const [x, y] = at(e.cause_pos);
          return (
            <circle key={`k${e.seq}`} cx={x} cy={y} r={4} className="fill-gold" fillOpacity={0.85}>
              <title>{`${duration(e.t_ms)}  ${eventLine(e, nameOf)}`}</title>
            </circle>
          );
        })}
        {[...kills, ...deaths].map((e) => {
          const [x, y] = at(e.effect_pos!);
          return (
            <circle key={`d${e.seq}`} cx={x} cy={y} r={4.5} fill="#ef4444" fillOpacity={0.8}>
              <title>{`${duration(e.t_ms)}  ${eventLine(e, nameOf) ?? `${nameOf(e.effect)} died`}`}</title>
            </circle>
          );
        })}
      </svg>
      <figcaption className="mt-2 flex gap-4 text-xs text-text-muted">
        <span className="flex items-center gap-1.5"><span className="inline-block w-2.5 h-2.5 rounded-full bg-gold" /> killer</span>
        <span className="flex items-center gap-1.5"><span className="inline-block w-2.5 h-2.5 rounded-full bg-red-500" /> death</span>
        <span>Top-down; hover a dot for the kill.</span>
      </figcaption>
    </figure>
  );
}
