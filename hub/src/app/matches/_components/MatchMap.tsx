"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

import type { DeathMark, KillMark } from "./positions";
import type { Hover, MapViewer, ViewMode } from "./mapViewer";

/**
 * The kills and deaths over the map they happened on: a top-down minimap,
 * or the level in 3D to orbit. The map is a converted map's preview model
 * (public/map-previews/<CODE>.glb, map-previews.json); three.js loads with
 * the first one drawn. Without WebGL, or if the model fails, `fallback`
 * (the plain plot) shows instead.
 */
export function MatchMap({
  code,
  kills,
  deaths,
  time,
  fresh,
  fallback,
}: {
  code: string;
  kills: KillMark[];
  deaths: DeathMark[];
  /** The replay's time, ms (null: the whole match), and how long a mark looks new. */
  time: number | null;
  fresh: number;
  fallback: ReactNode;
}) {
  const box = useRef<HTMLDivElement>(null);
  const [viewer, setViewer] = useState<MapViewer | null>(null);
  const [failed, setFailed] = useState(false);
  const [mode, setMode] = useState<ViewMode>("top");
  const [cut, setCut] = useState(1);
  const [hover, setHover] = useState<Hover>(null);

  useEffect(() => {
    let live = true;
    let made: MapViewer | null = null;
    (async () => {
      const { MapViewer } = await import("./mapViewer");
      made = await MapViewer.create(box.current!, `/map-previews/${code}.glb`, setHover);
      if (live) setViewer(made);
      else made.dispose();
    })().catch((e) => {
      console.warn(`map preview ${code}:`, e);
      if (live) setFailed(true);
    });
    return () => {
      live = false;
      made?.dispose();
      setViewer(null);
    };
  }, [code]);

  useEffect(() => viewer?.setMarks(kills, deaths), [viewer, kills, deaths]);
  useEffect(() => viewer?.setMode(mode), [viewer, mode]);
  useEffect(() => viewer?.setCut(cut), [viewer, cut]);
  useEffect(() => viewer?.setTime(time, fresh), [viewer, time, fresh]);

  if (failed) return <>{fallback}</>;

  const tab = (m: ViewMode, label: string) => (
    <button
      type="button"
      onClick={() => setMode(m)}
      aria-pressed={mode === m}
      className={`px-3 py-1 rounded-md ${mode === m ? "bg-gold/15 text-gold" : "text-text-muted hover:text-foreground"}`}
    >
      {label}
    </button>
  );

  return (
    <figure>
      <div className="mb-2 flex flex-wrap items-center gap-3 text-xs">
        <div className="flex rounded-lg border border-border p-0.5" role="group" aria-label="View">
          {tab("top", "Map")}
          {tab("3d", "3D")}
        </div>
        <label className="flex items-center gap-2 text-text-muted" title="Take off everything above a height, to see a lower floor">
          Cut
          <input
            type="range"
            min={0.05}
            max={1}
            step={0.01}
            value={cut}
            onChange={(e) => setCut(Number(e.target.value))}
            className="w-28 accent-[var(--color-gold)]"
            aria-label="Cut height"
          />
        </label>
        <button
          type="button"
          onClick={() => {
            setCut(1);
            viewer?.reset();
          }}
          className="text-text-muted hover:text-foreground"
        >
          Reset
        </button>
      </div>
      <div
        ref={box}
        className="relative aspect-square w-full max-w-xl overflow-hidden rounded-xl border border-border bg-surface"
        role="img"
        aria-label={`Kill and death positions on the map, ${mode === "top" ? "top-down" : "in 3D"}`}
      >
        {!viewer && (
          <p className="absolute inset-0 flex items-center justify-center text-sm text-text-muted">Loading map…</p>
        )}
        {hover && (
          <div
            className="pointer-events-none absolute z-10 max-w-[80%] rounded-md border border-border bg-background/95 px-2 py-1 text-xs text-foreground shadow"
            style={{
              top: hover.y + 12,
              ...(hover.flip ? { right: `calc(100% - ${hover.x - 12}px)` } : { left: hover.x + 12 }),
            }}
          >
            {hover.text}
          </div>
        )}
      </div>
      <figcaption className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-muted">
        <span className="flex items-center gap-1.5"><span className="inline-block w-2.5 h-2.5 rounded-full bg-gold" /> killer</span>
        <span className="flex items-center gap-1.5"><span className="inline-block w-2.5 h-2.5 rounded-full bg-red-500" /> death</span>
        <span>
          {mode === "top" ? "Drag to pan, scroll to zoom" : "Drag to orbit, right-drag to pan, scroll to zoom"}; hover a
          dot for the kill.
        </span>
      </figcaption>
    </figure>
  );
}
