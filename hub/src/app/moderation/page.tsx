"use client";

/**
 * The moderator's desk: gallery submissions awaiting review, and the
 * report queue. Every button here is a moderator-only API call — the
 * server enforces the role; this page just refuses to render for anyone
 * else so nobody stares at a wall of 403s.
 */
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Check, ShieldCheck, X } from "lucide-react";

import { Navbar } from "../components/Navbar";
import { Footer } from "../components/Footer";
import { useHub } from "../components/HubKit";
import type { QueuedMedia, Report } from "@mjolnir/hub-kit";
import { formatBytes } from "@mjolnir/hub-kit";

export default function ModerationPage() {
  const { client, user, ready, signIn } = useHub();
  const [queue, setQueue] = useState<QueuedMedia[] | null>(null);
  const [reports, setReports] = useState<Report[] | null>(null);
  const [banner, setBanner] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const isModerator = user !== null && user.role !== "user";

  const load = useCallback(() => {
    if (!isModerator) return;
    client
      .listModerationMedia("pending")
      .then(setQueue)
      .catch((e) => setBanner(e instanceof Error ? e.message : String(e)));
    client
      .listReports("open")
      .then(setReports)
      .catch((e) => setBanner(e instanceof Error ? e.message : String(e)));
  }, [client, isModerator]);

  useEffect(load, [load]);

  const decideMedia = async (id: string, action: "approve" | "reject") => {
    setBusy(id);
    setBanner(null);
    try {
      await client.decideMedia(id, action);
      setQueue((q) => (q ? q.filter((m) => m.id !== id) : q));
    } catch (e) {
      setBanner(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const decideReport = async (id: string, action: "resolve" | "dismiss") => {
    setBusy(id);
    setBanner(null);
    try {
      await client.decideReport(id, action);
      setReports((r) => (r ? r.filter((x) => x.id !== id) : r));
    } catch (e) {
      setBanner(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  return (
    <>
      <Navbar />
      <main className="pt-32 md:pt-36 pb-16 px-6 max-w-4xl mx-auto">
        <div className="flex items-center gap-3 mb-8">
          <ShieldCheck className="w-7 h-7 text-gold" />
          <h1 className="text-3xl font-black text-foreground">Moderation</h1>
        </div>

        {!ready ? (
          <p className="text-text-dim">Loading…</p>
        ) : !user ? (
          <p className="text-text-muted">
            <button onClick={signIn} className="text-gold hover:underline cursor-pointer">
              Sign in
            </button>{" "}
            to continue.
          </p>
        ) : !isModerator ? (
          <p className="text-text-muted">Moderators only.</p>
        ) : (
          <>
            {banner && (
              <div className="mb-6 rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-2 text-sm text-red-300">
                {banner}
              </div>
            )}

            {/* ── Gallery queue ── */}
            <section className="mb-12">
              <h2 className="text-sm font-bold uppercase text-text-dim mb-3">
                Gallery submissions{queue ? ` · ${queue.length}` : ""}
              </h2>

              {queue === null ? (
                <p className="text-text-dim text-sm">Loading…</p>
              ) : queue.length === 0 ? (
                <p className="text-text-dim text-sm">Queue is empty. Good.</p>
              ) : (
                <div className="space-y-4">
                  {queue.map((m) => (
                    <div key={m.id} className="rounded-lg border border-border p-4 flex flex-wrap gap-4">
                      {m.kind === "video" ? (
                        <video
                          src={m.url}
                          controls
                          preload="metadata"
                          className="w-full sm:w-64 rounded-lg border border-border"
                        />
                      ) : (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={m.url}
                          alt={m.alt_text}
                          className="w-full sm:w-64 rounded-lg border border-border object-cover"
                        />
                      )}
                      <div className="flex-1 min-w-48">
                        <p className="text-sm text-foreground mb-1">{m.alt_text}</p>
                        <p className="text-xs text-text-dim mb-3">
                          {m.kind} · {m.file_size ? formatBytes(m.file_size) : "size unknown"} · by{" "}
                          <span className="text-text-muted">{m.uploader}</span> · for{" "}
                          <Link href={`/mods/${m.mod_slug}`} className="text-gold hover:underline">
                            {m.mod_name}
                          </Link>
                        </p>
                        <div className="flex gap-2">
                          <button
                            onClick={() => decideMedia(m.id, "approve")}
                            disabled={busy === m.id}
                            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-green-500/15 text-green-400 hover:bg-green-500/25 disabled:opacity-40 transition-colors cursor-pointer"
                          >
                            <Check className="w-3.5 h-3.5" />
                            Approve
                          </button>
                          <button
                            onClick={() => decideMedia(m.id, "reject")}
                            disabled={busy === m.id}
                            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-red-500/15 text-red-400 hover:bg-red-500/25 disabled:opacity-40 transition-colors cursor-pointer"
                          >
                            <X className="w-3.5 h-3.5" />
                            Reject
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>

            {/* ── Reports ── */}
            <section>
              <h2 className="text-sm font-bold uppercase text-text-dim mb-3">
                Open reports{reports ? ` · ${reports.length}` : ""}
              </h2>

              {reports === null ? (
                <p className="text-text-dim text-sm">Loading…</p>
              ) : reports.length === 0 ? (
                <p className="text-text-dim text-sm">Nothing reported.</p>
              ) : (
                <div className="space-y-3">
                  {reports.map((r) => (
                    <div key={r.id} className="rounded-lg border border-border p-4">
                      <div className="flex flex-wrap items-center gap-2 mb-1">
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-red-500/15 text-red-400">
                          {r.reason}
                        </span>
                        <span className="text-xs text-text-dim">
                          {r.subject_type} <span className="font-mono">{r.subject_id.slice(0, 8)}…</span>{" "}
                          reported by <span className="text-text-muted">{r.reporter}</span>
                        </span>
                      </div>
                      {r.detail && <p className="text-sm text-text-muted mb-2">{r.detail}</p>}
                      <div className="flex gap-2">
                        <button
                          onClick={() => decideReport(r.id, "resolve")}
                          disabled={busy === r.id}
                          className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-green-500/15 text-green-400 hover:bg-green-500/25 disabled:opacity-40 transition-colors cursor-pointer"
                        >
                          Resolve
                        </button>
                        <button
                          onClick={() => decideReport(r.id, "dismiss")}
                          disabled={busy === r.id}
                          className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-surface-card text-text-muted hover:text-foreground disabled:opacity-40 transition-colors cursor-pointer"
                        >
                          Dismiss
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>
          </>
        )}
      </main>
      <Footer />
    </>
  );
}
