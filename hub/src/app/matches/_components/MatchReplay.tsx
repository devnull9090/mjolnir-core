"use client";

import { useEffect, useRef, useState } from "react";
import { Pause, Play } from "lucide-react";

import { duration } from "./format";
import { MatchMap } from "./MatchMap";
import { PositionMap } from "./PositionMap";
import type { DeathMark, KillMark } from "./positions";

/** A line of the timeline, worded by the server. */
export type TimelineRow = {
  seq: number;
  t_ms: number;
  text: string;
  /** A kill, suicide or death: drawn brighter than the rest. */
  strong: boolean;
  /** Involves the player the page is narrowed to. */
  mine: boolean;
};

const SPEEDS = [10, 30, 60, 120];

/** About a minute to play the whole match. */
function defaultSpeed(ms: number): number {
  const want = ms / 60000;
  return SPEEDS.reduce((best, s) => (Math.abs(s - want) < Math.abs(best - want) ? s : best));
}

/**
 * The kills and deaths on the map beside the match's timeline, with a
 * replay: play or scrub the match and the map shows only what had happened
 * by then (the last moments larger, the rest faded), the scrub bar marks
 * when each kill and death came, and the timeline follows. A timeline row
 * jumps the replay to it. Without a replay time, everything shows, as before.
 */
export function MatchReplay({
  code,
  kills,
  deaths,
  rows,
  durationMs,
  mapHeading,
  matchId,
  otherCount,
}: {
  /** The map's preview model, or null to draw the plain plot. */
  code: string | null;
  kills: KillMark[];
  deaths: DeathMark[];
  rows: TimelineRow[];
  durationMs: number;
  mapHeading: string;
  matchId: string;
  /** Incidents the timeline leaves out. */
  otherCount: number;
}) {
  const [time, setTime] = useState<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(() => defaultSpeed(durationMs));
  const end = Math.max(durationMs, ...rows.map((r) => r.t_ms), 1);
  // Long enough to see on the map while playing: a second and a half.
  const fresh = Math.max(8000, speed * 1500);

  // The playing loop starts from wherever the replay was left.
  const timeNow = useRef(time);
  useEffect(() => {
    timeNow.current = time;
  }, [time]);

  useEffect(() => {
    if (!playing) return;
    let frame = 0;
    let last = performance.now();
    let t = timeNow.current ?? 0;
    const tick = (now: number) => {
      t = Math.min(end, t + (now - last) * speed);
      last = now;
      setTime(t);
      if (t >= end) setPlaying(false);
      else frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing, speed, end]);

  // The row the replay is at: the last one by then.
  let current = -1;
  if (time !== null) for (let i = 0; i < rows.length && rows[i].t_ms <= time; i++) current = i;

  // Keep it in view in the list, without scrolling the page.
  const list = useRef<HTMLOListElement>(null);
  useEffect(() => {
    const ol = list.current;
    const li = current >= 0 ? (ol?.children[current] as HTMLElement | undefined) : undefined;
    if (!ol || !li) return;
    if (li.offsetTop < ol.scrollTop || li.offsetTop + li.offsetHeight > ol.scrollTop + ol.clientHeight) {
      ol.scrollTo({ top: li.offsetTop - ol.clientHeight / 2, behavior: playing ? "auto" : "smooth" });
    }
  }, [current, playing]);

  const toggle = () => {
    if (!playing && (time === null || time >= end)) {
      setTime(0);
      timeNow.current = 0;
    }
    setPlaying(!playing);
  };
  const seek = (t: number) => {
    setPlaying(false);
    setTime(t);
  };

  const plot = <PositionMap kills={kills} deaths={deaths} time={time} fresh={fresh} />;
  const hasPositions = kills.length + deaths.length > 0;
  const ticks = [
    ...kills.map((k) => ({ seq: k.seq, t: k.t_ms, kill: true })),
    ...deaths.map((d) => ({ seq: d.seq, t: d.t_ms, kill: false })),
  ];

  return (
    <div className="grid gap-10 lg:grid-cols-2">
      <section id="map">
        <h2 className="text-sm font-bold uppercase text-text-dim mb-3">{mapHeading}</h2>
        {hasPositions && code ? (
          <MatchMap code={code} kills={kills} deaths={deaths} time={time} fresh={fresh} fallback={plot} />
        ) : (
          plot
        )}
        {hasPositions && (
          <div className="mt-4 max-w-xl">
            <div className="flex items-center gap-3 text-xs">
              <button
                type="button"
                onClick={toggle}
                className="flex h-8 w-8 items-center justify-center rounded-full bg-gold text-background hover:bg-gold-dim"
                aria-label={playing ? "Pause the replay" : "Play the replay"}
              >
                {playing ? <Pause size={14} fill="currentColor" /> : <Play size={14} fill="currentColor" className="ml-0.5" />}
              </button>
              <span className="tabular-nums text-foreground">
                {time === null ? "Whole match" : duration(time)}
                <span className="text-text-dim"> / {duration(end)}</span>
              </span>
              <div className="ml-auto flex items-center gap-1" role="group" aria-label="Replay speed">
                {SPEEDS.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => setSpeed(s)}
                    aria-pressed={speed === s}
                    className={`rounded px-1.5 py-0.5 tabular-nums ${speed === s ? "bg-gold/15 text-gold" : "text-text-muted hover:text-foreground"}`}
                  >
                    {s}×
                  </button>
                ))}
              </div>
              <button
                type="button"
                onClick={() => {
                  setPlaying(false);
                  setTime(null);
                }}
                disabled={time === null}
                className="text-text-muted hover:text-foreground disabled:opacity-40"
              >
                Show all
              </button>
            </div>
            <div className="relative mt-2 h-7">
              {/* When each kill (gold) and death (red) came. */}
              <div className="pointer-events-none absolute inset-x-0 top-0 h-3" aria-hidden>
                {ticks.map((k) => (
                  <span
                    key={`${k.kill ? "k" : "d"}${k.seq}`}
                    className={`absolute top-0 h-3 w-0.5 -translate-x-1/2 rounded-full ${k.kill ? "bg-gold" : "bg-red-500"} ${time !== null && k.t > time ? "opacity-30" : "opacity-90"}`}
                    style={{ left: `${(k.t / end) * 100}%` }}
                  />
                ))}
              </div>
              <input
                type="range"
                min={0}
                max={end}
                step={100}
                value={time ?? end}
                onChange={(e) => seek(Number(e.target.value))}
                className="absolute inset-x-0 bottom-0 w-full accent-[var(--color-gold)]"
                aria-label="Replay time"
              />
            </div>
          </div>
        )}
      </section>

      <section>
        <h2 className="text-sm font-bold uppercase text-text-dim mb-3">Timeline</h2>
        {rows.length === 0 ? (
          <p className="text-sm text-text-muted">Nothing happened.</p>
        ) : (
          <ol
            ref={list}
            className="relative max-h-[560px] overflow-y-auto rounded-xl border border-border divide-y divide-border text-sm"
          >
            {rows.map((r, i) => {
              const future = time !== null && r.t_ms > time;
              const now = i === current;
              return (
                <li key={r.seq}>
                  <button
                    type="button"
                    onClick={() => seek(r.t_ms)}
                    title="Replay from here"
                    className={`flex w-full gap-3 px-4 py-2 text-left border-l-2 hover:bg-surface-raised ${
                      now ? "border-l-gold bg-gold/15" : `border-l-transparent ${r.mine ? "bg-gold/10" : ""}`
                    } ${future ? "opacity-40" : ""}`}
                  >
                    <span className="w-12 shrink-0 tabular-nums text-text-dim">{duration(r.t_ms)}</span>
                    <span className={r.strong ? "text-foreground" : "text-text-muted"}>{r.text}</span>
                  </button>
                </li>
              );
            })}
          </ol>
        )}
        {otherCount > 0 && (
          <p className="mt-2 text-xs text-text-dim">
            Plus {otherCount} other incidents (spawns, deaths a kill already tells, commendations, lead changes) in
            the{" "}
            <a href={`/api/v1/matches/${matchId}`} className="underline hover:text-foreground">
              full event data
            </a>
            .
          </p>
        )}
      </section>
    </div>
  );
}
