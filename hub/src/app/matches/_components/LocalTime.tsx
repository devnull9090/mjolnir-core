"use client";

import { useSyncExternalStore } from "react";

import { sqlDate, when } from "./format";

// One clock for every time on the page, ticking each minute so "ago" stays true.
const listeners = new Set<() => void>();
let timer: ReturnType<typeof setInterval> | undefined;

function subscribe(listener: () => void) {
  listeners.add(listener);
  timer ??= setInterval(() => listeners.forEach((l) => l()), 60_000);
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0) {
      clearInterval(timer);
      timer = undefined;
    }
  };
}

const minute = () => Math.floor(Date.now() / 60_000);

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["year", 365 * 86400],
  ["month", 30 * 86400],
  ["week", 7 * 86400],
  ["day", 86400],
  ["hour", 3600],
  ["minute", 60],
];

function ago(d: Date, now: number): string {
  const s = Math.round((now - d.getTime()) / 1000);
  if (s < 60) return "just now";
  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  const [unit, size] = UNITS.find(([, size]) => s >= size)!;
  return rtf.format(-Math.floor(s / size), unit);
}

/**
 * A stored UTC time ("2026-10-03 21:14:05") in the reader's own time zone,
 * with how long ago it was. The server renders it in UTC, as before; the
 * browser swaps in its local time once it hydrates.
 */
export function LocalTime({ sql, showAgo = true }: { sql: string; showAgo?: boolean }) {
  const now = useSyncExternalStore(subscribe, minute, () => null);
  const d = sqlDate(sql);
  if (!d || now === null) return <time dateTime={d?.toISOString()}>{when(sql)}</time>;
  const local = d.toLocaleString(undefined, {
    year: new Date().getFullYear() === d.getFullYear() ? undefined : "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
  const full = d.toLocaleString(undefined, { dateStyle: "full", timeStyle: "long" });
  return (
    <time dateTime={d.toISOString()} title={full}>
      {local}
      {showAgo && <span className="ml-2 text-xs font-normal text-text-dim">{ago(d, now * 60_000)}</span>}
    </time>
  );
}
