/**
 * Download and disk speeds for the Updates screen, Steam-style.
 *
 * The installers only report how many bytes they have moved so far
 * (`transfer` events from src-tauri/src/transfer.rs). Speed is a question
 * about time, so it is answered here: the counts are sampled on a fixed
 * clock, and the difference between samples is the rate. That keeps the
 * graph's bars evenly spaced however bursty the events are.
 */
import { useEffect, useRef, useState } from "react";
import { listen } from "@tauri-apps/api/event";

/** One task's running counts, as the backend reports them. */
export interface TransferReport {
  task: string;
  received: number;
  /** Null while the size of something it is fetching is unknown. */
  total: number | null;
  written: number;
}

export interface TaskTransfer {
  received: number;
  total: number | null;
  written: number;
  /** Bytes per second, smoothed so the row's number is readable. */
  rate: number;
}

export interface Sample {
  /** Bytes per second over one sample period. */
  net: number;
  disk: number;
}

export interface TransferStats {
  tasks: Record<string, TaskTransfer>;
  /** Oldest first, at most `HISTORY` samples. */
  history: Sample[];
  current: number;
  peak: number;
  diskRate: number;
  received: number;
  written: number;
  /** Milliseconds since the run started, frozen when it ends. */
  elapsed: number;
}

export const SAMPLE_MS = 500;
/** One minute of samples, which is what the graph shows. */
export const HISTORY = 120;

const EMPTY: TransferStats = {
  tasks: {},
  history: [],
  current: 0,
  peak: 0,
  diskRate: 0,
  received: 0,
  written: 0,
  elapsed: 0,
};

/**
 * The launcher's own update downloads through the updater plugin in the
 * webview, not through code that can emit `transfer`; it reports here.
 */
const localListeners = new Set<(r: TransferReport) => void>();
export function reportTransfer(report: TransferReport) {
  for (const l of localListeners) l(report);
}

/**
 * Track every transfer while `active`. A new run (active turning true)
 * starts from zero; when it ends the last numbers stay up as a summary.
 */
export function useTransfers(active: boolean): TransferStats {
  const latest = useRef(new Map<string, TransferReport>());
  const [stats, setStats] = useState<TransferStats>(EMPTY);

  useEffect(() => {
    const take = (r: TransferReport) => latest.current.set(r.task, r);
    localListeners.add(take);
    const stop = listen<TransferReport>("transfer", (e) => take(e.payload));
    return () => {
      localListeners.delete(take);
      void stop.then((unlisten) => unlisten());
    };
  }, []);

  useEffect(() => {
    if (!active) return;
    latest.current.clear();
    setStats(EMPTY);

    const started = performance.now();
    let last = started;
    let prevReceived = 0;
    let prevWritten = 0;
    const prevTask = new Map<string, number>();
    const rates = new Map<string, number>();

    const timer = window.setInterval(() => {
      const now = performance.now();
      const dt = (now - last) / 1000;
      last = now;
      if (dt <= 0) return;

      let received = 0;
      let written = 0;
      const tasks: Record<string, TaskTransfer> = {};
      for (const [task, r] of latest.current) {
        received += r.received;
        written += r.written;
        const instant = Math.max(0, r.received - (prevTask.get(task) ?? 0)) / dt;
        prevTask.set(task, r.received);
        // Smoothed over about two seconds: the bars show the raw samples,
        // the row's number is for reading.
        const rate = (rates.get(task) ?? instant) * 0.75 + instant * 0.25;
        rates.set(task, rate);
        tasks[task] = { received: r.received, total: r.total, written: r.written, rate };
      }

      const sample: Sample = {
        net: Math.max(0, received - prevReceived) / dt,
        disk: Math.max(0, written - prevWritten) / dt,
      };
      prevReceived = received;
      prevWritten = written;

      setStats((s) => {
        const history = [...s.history, sample].slice(-HISTORY);
        // "Current" averages the last second, as Steam's does; one sample
        // swings with every chunk boundary.
        const recent = history.slice(-2);
        const current = recent.reduce((a, x) => a + x.net, 0) / recent.length;
        return {
          tasks,
          history,
          current,
          peak: Math.max(s.peak, current),
          diskRate: recent.reduce((a, x) => a + x.disk, 0) / recent.length,
          received,
          written,
          elapsed: now - started,
        };
      });
    }, SAMPLE_MS);

    return () => {
      window.clearInterval(timer);
      // The run is over: nothing is moving, whatever the last sample said.
      setStats((s) => ({ ...s, current: 0, diskRate: 0 }));
    };
  }, [active]);

  return stats;
}

export function formatBytes(n: number): string {
  if (n >= 1024 ** 3) return `${(n / 1024 ** 3).toFixed(2)} GB`;
  if (n >= 1024 ** 2) return `${(n / 1024 ** 2).toFixed(1)} MB`;
  if (n >= 1024) return `${Math.round(n / 1024)} KB`;
  return `${Math.round(n)} B`;
}

export function formatRate(bytesPerSecond: number): string {
  return `${formatBytes(bytesPerSecond)}/s`;
}

export function formatDuration(ms: number): string {
  const s = Math.max(0, Math.round(ms / 1000));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = String(s % 60).padStart(2, "0");
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${sec}` : `${m}:${sec}`;
}
