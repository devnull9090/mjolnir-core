/**
 * The game's crashes, as the Rust side finds them (src-tauri/src/crash.rs,
 * docs/crash_reports.md). The banner and the Settings list both read them
 * through `useCrashes`; anything that changes a crash tells every reader to
 * read again.
 */
import { useCallback, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";

export interface Crash {
  id: string;
  /** Unix seconds. */
  crashed_at: number;
  /** "Crash", "Assert", "GPUCrash", "Ensure", ... */
  crash_type: string;
  error_message: string;
  build_version: string;
  seconds_since_start: number | null;
  /** "multiplayer", "campaign", or the film's own word. */
  mode: string | null;
  /** Scenario code, lower case. */
  map: string | null;
  map_name: string | null;
  role: string | null;
  fault: string;
  signature: string;
  dump_bytes: number;
  folder: string;
  log_saved: boolean;
  status: "new" | "old" | "dismissed" | "sent";
  report_id: string | null;
  /** The hub asked for the full dump and the player has not answered. */
  dump_requested: boolean;
  dump_sent: boolean;
}

export interface SendResult {
  report_id: string;
  dump_requested: boolean;
  dump_bytes: number;
}

const CHANGED = "mjolnir-crashes-changed";

function changed() {
  window.dispatchEvent(new Event(CHANGED));
}

export function useCrashes() {
  const [crashes, setCrashes] = useState<Crash[] | null>(null);
  const refresh = useCallback(
    () =>
      invoke<Crash[]>("crash_list").then(
        (list) => setCrashes(list),
        () => setCrashes([]),
      ),
    [],
  );
  useEffect(() => {
    void refresh();
    const onChange = () => void refresh();
    window.addEventListener(CHANGED, onChange);
    // The watcher found one while the launcher was open.
    const stop = listen("crash-detected", onChange);
    return () => {
      window.removeEventListener(CHANGED, onChange);
      void stop.then((unlisten) => unlisten());
    };
  }, [refresh]);
  return { crashes, refresh };
}

export async function sendCrash(id: string): Promise<SendResult> {
  try {
    return await invoke<SendResult>("crash_send", { id });
  } finally {
    changed();
  }
}

export async function sendCrashDump(id: string): Promise<void> {
  try {
    await invoke("crash_send_dump", { id });
  } finally {
    changed();
  }
}

export async function declineCrashDump(id: string): Promise<void> {
  await invoke("crash_decline_dump", { id });
  changed();
}

export async function dismissCrash(id: string): Promise<void> {
  await invoke("crash_dismiss", { id });
  changed();
}

const SIGNED_OUT = "signed_out:";

/** The Rust side's way of saying "sign in first". */
export function isSignedOut(error: unknown): boolean {
  return String(error).startsWith(SIGNED_OUT);
}

export function errorText(error: unknown): string {
  const text = String(error);
  return text.startsWith(SIGNED_OUT) ? text.slice(SIGNED_OUT.length).trim() : text;
}

function duration(seconds: number): string {
  if (seconds < 90) return `${seconds} second${seconds === 1 ? "" : "s"}`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 90) return `${minutes} minutes`;
  const hours = Math.round(minutes / 6) / 10;
  return `${hours} hours`;
}

function where(c: Crash): string {
  const map = c.map_name ?? c.map?.toUpperCase();
  const on = map ? ` on ${map}` : "";
  if (c.mode === "multiplayer") return `a multiplayer game${on}`;
  if (c.mode === "campaign") return `the campaign${on}`;
  return map ? map : "the game";
}

/** "3 minutes into a multiplayer game on BCK". */
export function crashPlace(c: Crash): string {
  const place = where(c);
  return c.seconds_since_start != null ? `${duration(c.seconds_since_start)} into ${place}` : `in ${place}`;
}

export function crashKind(c: Crash): string {
  switch (c.crash_type) {
    case "GPUCrash":
      return "Graphics crash";
    case "Assert":
      return "Assertion";
    case "Ensure":
      return "Warning";
    case "Stall":
      return "Hang";
    default:
      return "Crash";
  }
}

export function formatBytes(n: number): string {
  if (n >= 1 << 30) return `${(n / (1 << 30)).toFixed(1)} GB`;
  if (n >= 1 << 20) return `${Math.round(n / (1 << 20))} MB`;
  return `${Math.max(1, Math.round(n / 1024))} KB`;
}

/** Zipped, the full dump is about a third of its size on disk. */
export function zippedDumpSize(c: Crash): string {
  return formatBytes(c.dump_bytes / 3);
}

export function formatWhen(unix: number): string {
  return new Date(unix * 1000).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}
