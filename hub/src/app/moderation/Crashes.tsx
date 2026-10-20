"use client";

/**
 * Launcher crash reports, grouped by signature and build (docs/crash_reports.md).
 *
 * Admins only: a bundle carries a player's UE4SS log and a full dump is a
 * copy of the game's memory, which the moderation queues never needed.
 * Opening a signature lists its reports, each with its bundle and, when the
 * hub asked for one and the player agreed, its full dump.
 */
import { useCallback, useEffect, useState } from "react";
import { ChevronDown, ChevronRight, Download } from "lucide-react";

import type { CrashReport, CrashSignature, HubClient } from "@mjolnir/hub-kit";
import { formatBytes } from "@mjolnir/hub-kit";

/** `2026.08.11.1121610.2-Rel-i343-Meteorite-2607-CU4` → `CU4`. */
function shortBuild(build: string): string {
  return build.match(/-(CU\d+)$/)?.[1] ?? build;
}

function when(iso: string): string {
  return iso.slice(0, 16).replace("T", " ");
}

const TYPE_STYLE: Record<string, string> = {
  Crash: "bg-red-500/15 text-red-400",
  GPUCrash: "bg-purple-500/15 text-purple-300",
  Assert: "bg-amber-500/15 text-amber-300",
};

function Reports({ client, signature, onError }: { client: HubClient; signature: CrashSignature; onError: (m: string) => void }) {
  const [reports, setReports] = useState<CrashReport[] | null>(null);

  useEffect(() => {
    client
      .listCrashReports(signature.signature, signature.build_version)
      .then(setReports)
      .catch((e) => onError(e instanceof Error ? e.message : String(e)));
  }, [client, signature, onError]);

  if (reports === null) return <p className="text-text-dim text-xs px-4 pb-3">Loading…</p>;
  return (
    <div className="px-4 pb-3 space-y-2">
      {reports.map((r) => (
        <div key={r.id} className="rounded-lg bg-surface-card px-3 py-2 text-xs flex flex-wrap items-center gap-x-4 gap-y-1">
          <span className="text-foreground">{r.user.name}</span>
          <span className="text-text-dim">{when(r.crashed_at)} UTC</span>
          {r.seconds_since_start !== null && (
            <span className="text-text-dim">{Math.round(r.seconds_since_start / 60)} min in</span>
          )}
          {(r.mode || r.map) && (
            <span className="text-text-muted">
              {[r.mode, r.map?.toUpperCase()].filter(Boolean).join(" · ")}
            </span>
          )}
          {r.launcher_version && <span className="text-text-dim">launcher {r.launcher_version}</span>}
          <span className="ml-auto flex gap-2">
            {r.has_bundle ? (
              <a href={client.crashFileUrl(r.id, "bundle")} className="flex items-center gap-1 text-gold hover:underline">
                <Download className="w-3 h-3" />
                Bundle{r.bundle_bytes ? ` (${formatBytes(r.bundle_bytes)})` : ""}
              </a>
            ) : (
              <span className="text-text-dim">no bundle yet</span>
            )}
            {r.has_dump ? (
              <a href={client.crashFileUrl(r.id, "dump")} className="flex items-center gap-1 text-gold hover:underline">
                <Download className="w-3 h-3" />
                Dump{r.dump_zip_bytes ? ` (${formatBytes(r.dump_zip_bytes)})` : ""}
              </a>
            ) : (
              r.dump_wanted && <span className="text-text-dim">dump asked for</span>
            )}
          </span>
        </div>
      ))}
    </div>
  );
}

export function Crashes({ client, onError }: { client: HubClient; onError: (message: string | null) => void }) {
  const [signatures, setSignatures] = useState<CrashSignature[] | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  const fail = useCallback((e: unknown) => onError(e instanceof Error ? e.message : String(e)), [onError]);

  useEffect(() => {
    client.listCrashSignatures().then(setSignatures).catch(fail);
  }, [client, fail]);

  const total = signatures?.reduce((n, s) => n + s.reports, 0) ?? 0;

  return (
    <section>
      <h2 className="text-sm font-bold uppercase text-text-dim mb-3">
        Crash reports{signatures ? ` · ${total} in ${signatures.length} signatures` : ""}
      </h2>
      {signatures === null ? (
        <p className="text-text-dim text-sm">Loading…</p>
      ) : signatures.length === 0 ? (
        <p className="text-text-dim text-sm">No crash reports.</p>
      ) : (
        <div className="space-y-2">
          {signatures.map((s) => {
            const key = `${s.signature}|${s.build_version}`;
            const isOpen = open === key;
            return (
              <div key={key} className="rounded-lg border border-border">
                <button
                  onClick={() => setOpen(isOpen ? null : key)}
                  className="w-full text-left p-3 flex items-start gap-3 cursor-pointer"
                >
                  {isOpen ? (
                    <ChevronDown className="w-4 h-4 mt-0.5 text-text-dim shrink-0" />
                  ) : (
                    <ChevronRight className="w-4 h-4 mt-0.5 text-text-dim shrink-0" />
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="text-sm text-foreground font-mono break-all">{s.fault}</p>
                    <p className="text-xs text-text-dim mt-1 flex flex-wrap gap-x-3">
                      <span
                        className={`px-1.5 py-0.5 rounded text-[10px] font-bold uppercase ${
                          TYPE_STYLE[s.crash_type] ?? "bg-surface-card text-text-muted"
                        }`}
                      >
                        {s.crash_type}
                      </span>
                      <span title={s.build_version}>{shortBuild(s.build_version)}</span>
                      <span>
                        {s.reports} report{s.reports === 1 ? "" : "s"} · {s.players} player{s.players === 1 ? "" : "s"}
                      </span>
                      <span>{s.dumps} dump{s.dumps === 1 ? "" : "s"}</span>
                      {s.maps.length > 0 && <span>{s.maps.map((m) => m.toUpperCase()).join(", ")}</span>}
                      <span>last {when(s.last_seen)}</span>
                      <span className="font-mono">{s.signature}</span>
                    </p>
                  </div>
                </button>
                {isOpen && <Reports client={client} signature={s} onError={fail} />}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
