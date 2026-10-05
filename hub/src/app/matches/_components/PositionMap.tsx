import type { DeathMark, KillMark, Point } from "./positions";

const SIZE = 560;
const PAD = 24;

/**
 * Where the kills and deaths happened, seen from above, without the map: the
 * map's Unreal X across and Y down, as the editor's top view draws it. A line
 * joins a killer (gold) to the victim (red). Drawn for a map the hub has no
 * preview model of, and while MatchMap cannot draw one (no WebGL).
 */
export function PositionMap({ kills, deaths }: { kills: KillMark[]; deaths: DeathMark[] }) {
  const points: Point[] = [
    ...kills.flatMap((k) => (k.from ? [k.to, k.from] : [k.to])),
    ...deaths.map((d) => d.at),
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
        {kills.map((k) => {
          if (!k.from) return null;
          const [x1, y1] = at(k.from);
          const [x2, y2] = at(k.to);
          return (
            <line key={`l${k.seq}`} x1={x1} y1={y1} x2={x2} y2={y2} stroke="currentColor" className="text-text-dim" strokeOpacity={0.35} strokeWidth={1} />
          );
        })}
        {kills.map((k) => {
          if (!k.from) return null;
          const [x, y] = at(k.from);
          return (
            <circle key={`k${k.seq}`} cx={x} cy={y} r={4} className="fill-gold" fillOpacity={0.85}>
              <title>{k.label}</title>
            </circle>
          );
        })}
        {[...kills.map((k) => ({ seq: k.seq, at: k.to, label: k.label })), ...deaths].map((d) => {
          const [x, y] = at(d.at);
          return (
            <circle key={`d${d.seq}`} cx={x} cy={y} r={4.5} fill="#ef4444" fillOpacity={0.8}>
              <title>{d.label}</title>
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
