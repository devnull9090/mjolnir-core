import type { DeathMark, KillMark, Point } from "./positions";

const SIZE = 560;
const PAD = 24;

/**
 * Where the kills and deaths happened, seen from above, without the map: the
 * map's Unreal X across and Y down, as the editor's top view draws it. A line
 * joins a killer (gold) to the victim (red). Drawn for a map the hub has no
 * preview model of, and while MatchMap cannot draw one (no WebGL).
 *
 * With a replay `time`, only what had happened by then, the last `fresh` ms
 * of it larger and the rest faded. The frame stays the whole match's.
 */
export function PositionMap({
  kills: allKills,
  deaths: allDeaths,
  time = null,
  fresh = 10000,
}: {
  kills: KillMark[];
  deaths: DeathMark[];
  time?: number | null;
  fresh?: number;
}) {
  const kills = time === null ? allKills : allKills.filter((k) => k.t_ms <= time);
  const deaths = time === null ? allDeaths : allDeaths.filter((d) => d.t_ms <= time);
  /** 1 for a mark that just happened, 0 for an old one (or no replay). */
  const freshness = (t: number) => (time === null ? 0 : Math.max(0, 1 - (time - t) / fresh));
  const opacity = (t: number) => (time === null ? 1 : 0.35 + 0.65 * freshness(t));
  const points: Point[] = [
    ...allKills.flatMap((k) => (k.from ? [k.to, k.from] : [k.to])),
    ...allDeaths.map((d) => d.at),
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
            <line key={`l${k.seq}`} x1={x1} y1={y1} x2={x2} y2={y2} stroke="currentColor" className="text-text-dim" strokeOpacity={0.35 * opacity(k.t_ms)} strokeWidth={1} />
          );
        })}
        {kills.map((k) => {
          if (!k.from) return null;
          const [x, y] = at(k.from);
          return (
            <circle key={`k${k.seq}`} cx={x} cy={y} r={4 * (1 + freshness(k.t_ms))} className="fill-gold" fillOpacity={0.85 * opacity(k.t_ms)}>
              <title>{k.label}</title>
            </circle>
          );
        })}
        {[...kills.map((k) => ({ seq: k.seq, t_ms: k.t_ms, at: k.to, label: k.label })), ...deaths].map((d) => {
          const [x, y] = at(d.at);
          return (
            <circle key={`d${d.seq}`} cx={x} cy={y} r={4.5 * (1 + freshness(d.t_ms))} fill="#ef4444" fillOpacity={0.8 * opacity(d.t_ms)}>
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
