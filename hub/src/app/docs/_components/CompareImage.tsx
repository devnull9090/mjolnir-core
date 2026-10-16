"use client";

import { useState } from "react";

/**
 * Two screenshots of one view, the "before" revealed over the "after" up to a
 * draggable divider. Written in Markdown as an ordinary image whose URL
 * carries the other one, so the post still reads on GitHub (it shows the
 * after shot):
 *
 *   ![Death Island, the beach](/blog-images/x/dti-beach.jpg?before=/blog-images/x/dti-beach-classic.jpg)
 *
 * Spans throughout: Markdown wraps a standalone image in a paragraph, where a
 * div is invalid HTML and a hydration error.
 */
export function CompareImage({
  before,
  after,
  alt,
  beforeLabel = "Classic",
  afterLabel = "Remastered",
}: {
  before: string;
  after: string;
  alt: string;
  beforeLabel?: string;
  afterLabel?: string;
}) {
  const [pos, setPos] = useState(50);
  const tag =
    "pointer-events-none absolute top-2 rounded bg-black/60 px-2 py-1 font-mono text-[10px] uppercase tracking-widest text-white";
  return (
    <span className="mt-6 block">
      <span className="relative block aspect-video w-full select-none overflow-hidden border border-border bg-surface">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={after} alt={`${alt} (${afterLabel.toLowerCase()})`} loading="lazy"
          className="pointer-events-none absolute inset-0 block h-full w-full object-cover" />
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={before} alt={`${alt} (${beforeLabel.toLowerCase()})`} loading="lazy"
          className="pointer-events-none absolute inset-0 block h-full w-full object-cover"
          style={{ clipPath: `inset(0 ${100 - pos}% 0 0)` }} />
        <span className="pointer-events-none absolute inset-y-0 block w-0.5 -translate-x-1/2 bg-white shadow-[0_0_6px_rgba(0,0,0,.6)]"
          style={{ left: `${pos}%` }}>
          <span className="absolute left-1/2 top-1/2 block -translate-x-1/2 -translate-y-1/2 whitespace-nowrap rounded-full bg-white px-2 py-1 font-mono text-xs font-bold text-black">
            ‹ ›
          </span>
        </span>
        <span className={`${tag} left-2`}>{beforeLabel}</span>
        <span className={`${tag} right-2`}>{afterLabel}</span>
        <input
          type="range"
          min={0}
          max={100}
          step={0.1}
          value={pos}
          onChange={(e) => setPos(Number(e.target.value))}
          aria-label={`${alt}: drag to compare ${beforeLabel.toLowerCase()} and ${afterLabel.toLowerCase()}`}
          className="absolute inset-0 h-full w-full cursor-ew-resize opacity-0"
        />
      </span>
      {alt && <span className="mt-2 block text-xs leading-6 text-text-dim">{alt}</span>}
    </span>
  );
}
