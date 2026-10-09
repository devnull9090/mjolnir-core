/**
 * The speed graph at the top of Updates, after Steam's download page: the
 * network as bars, the disk as a line, the last minute scrolling right to
 * left, and the numbers a player actually looks at beside it.
 */
import type { UpdateProgress } from "../updates/useUpdates";
import {
  HISTORY,
  formatBytes,
  formatDuration,
  formatRate,
  type TransferStats,
} from "../updates/useTransfers";

export default function TransferPanel({
  stats,
  applying,
  run,
  progress,
}: {
  stats: TransferStats;
  applying: boolean;
  run: string[];
  progress: Record<string, UpdateProgress>;
}) {
  const finished = run.filter((k) => {
    const s = progress[k]?.status;
    return s === "done" || s === "failed";
  }).length;
  const failed = run.filter((k) => progress[k]?.status === "failed").length;
  const current = run.find((k) => progress[k]?.status === "running");
  // The item in flight counts for however much of it has come down, so the
  // bar moves during a big download instead of jumping once at the end.
  const moving = current ? stats.tasks[current] : undefined;
  const partial =
    moving?.total && moving.total > 0 ? Math.min(1, moving.received / moving.total) : 0;
  const overall = run.length > 0 ? (finished + (current ? partial : 0)) / run.length : 0;

  return (
    <section className="rounded-xl border border-border-subtle bg-surface-secondary overflow-hidden">
      <div className="flex flex-col md:flex-row gap-5 p-4">
        <SpeedGraph stats={stats} />
        <div className="md:w-72 shrink-0 flex flex-col">
          <h3 className="text-lg font-bold">
            {applying ? "Downloading" : failed > 0 ? "Finished with errors" : "Finished"}
          </h3>
          <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-2">
            <Stat label="Current" value={formatRate(stats.current)} />
            <Stat label="Peak" value={formatRate(stats.peak)} />
            <Stat label="Total" value={formatBytes(stats.received)} />
            <Stat label="Disk usage" value={formatRate(stats.diskRate)} />
          </dl>
          <div className="mt-auto pt-3 flex items-center gap-4 text-[11px] uppercase tracking-wide text-text-secondary">
            <span className="flex items-center gap-1.5">
              <svg viewBox="0 0 10 10" className="w-3 h-3 text-accent-blue" aria-hidden>
                <rect x="0.5" y="5" width="2" height="5" fill="currentColor" />
                <rect x="4" y="1" width="2" height="9" fill="currentColor" />
                <rect x="7.5" y="3" width="2" height="7" fill="currentColor" />
              </svg>
              Network
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-3.5 h-0.5 rounded bg-accent-green" aria-hidden />
              Disk
            </span>
          </div>
        </div>
      </div>

      <div className="border-t border-border-subtle px-4 py-3">
        <div className="flex items-baseline justify-between gap-3 text-xs">
          <span className="font-semibold uppercase tracking-wide text-mjolnir-gold tabular-nums">
            {applying
              ? `Updating ${Math.min(finished + 1, run.length)} of ${run.length} · ${Math.floor(overall * 100)}%`
              : `${finished - failed} of ${run.length} updated`}
          </span>
          <span className="text-text-secondary font-mono tabular-nums">
            {formatDuration(stats.elapsed)} {applying ? "elapsed" : "total"}
          </span>
        </div>
        <div className="mt-1.5 h-1.5 rounded-full bg-surface-hover overflow-hidden">
          <div
            className={`h-full rounded-full transition-[width] duration-300 ease-out ${
              failed > 0 ? "bg-amber-500" : "bg-mjolnir-gold"
            }`}
            style={{ width: `${(applying ? overall : 1) * 100}%` }}
          />
        </div>
      </div>
    </section>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    // Value above label, as Steam has it; reversed visually so the markup
    // keeps dt before dd.
    <div className="flex flex-col-reverse">
      <dt className="text-[11px] uppercase tracking-wide text-text-secondary">{label}</dt>
      <dd className="text-base font-bold tabular-nums">{value}</dd>
    </div>
  );
}

/**
 * One bar per sample, newest at the right. The scale follows the busiest
 * sample on screen, so a slow connection still fills the graph.
 */
function SpeedGraph({ stats }: { stats: TransferStats }) {
  const { history } = stats;
  const top = Math.max(1024 * 1024, ...history.map((s) => Math.max(s.net, s.disk))) * 1.1;
  const offset = HISTORY - history.length;
  const y = (v: number) => 100 - (v / top) * 100;
  const disk = history.map((s, i) => `${offset + i + 0.5},${y(s.disk)}`).join(" ");

  return (
    <div className="relative flex-1 min-w-0 h-32 rounded-lg bg-surface-primary/60 border border-border-subtle overflow-hidden">
      <svg
        viewBox={`0 0 ${HISTORY} 100`}
        preserveAspectRatio="none"
        className="absolute inset-0 w-full h-full"
        role="img"
        aria-label={`Download speed over the last minute, now ${formatRate(stats.current)}`}
      >
        {[25, 50, 75].map((g) => (
          <line
            key={g}
            x1="0"
            x2={HISTORY}
            y1={g}
            y2={g}
            stroke="currentColor"
            className="text-border-subtle"
            strokeWidth="1"
            strokeDasharray="2 3"
            vectorEffect="non-scaling-stroke"
          />
        ))}
        {history.map((s, i) => {
          const h = (s.net / top) * 100;
          return h > 0 ? (
            <rect
              key={i}
              x={offset + i + 0.12}
              y={100 - h}
              width="0.76"
              height={h}
              className="fill-accent-blue/80"
            />
          ) : null;
        })}
        {history.length > 1 && (
          <polyline
            points={disk}
            fill="none"
            stroke="currentColor"
            className="text-accent-green"
            strokeWidth="2"
            strokeLinejoin="round"
            vectorEffect="non-scaling-stroke"
          />
        )}
        <line
          x1="0"
          x2={HISTORY}
          y1="100"
          y2="100"
          stroke="currentColor"
          className="text-accent-blue"
          strokeWidth="2"
          vectorEffect="non-scaling-stroke"
        />
      </svg>
      <span className="absolute top-1.5 left-2 text-[10px] font-mono text-text-secondary tabular-nums">
        {formatRate(top)}
      </span>
      {history.length === 0 && (
        <span className="absolute inset-0 grid place-items-center text-xs text-text-secondary">
          Waiting for the first bytes…
        </span>
      )}
    </div>
  );
}
