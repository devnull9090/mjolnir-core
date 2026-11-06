"use client";

/**
 * Releases held for a moderator: a map from a new author, or anything carrying
 * Wwise banks (docs/map_distribution.md). A held release stays out of players'
 * reach until someone approves it here.
 *
 * The archive can't be opened from this page, so a card shows what the scan
 * saw: the banks, which go to Wwise's own parser in every player's game, and
 * the findings. A decision carries the hash of the archive on the card, so a
 * replacement behind an open page is refused rather than approved unread.
 */
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle, Check, X } from "lucide-react";

import type { HubClient, QueuedRelease } from "@mjolnir/hub-kit";
import { formatBytes } from "@mjolnir/hub-kit";

const STATES = ["pending", "approved", "rejected"] as const;
type State = (typeof STATES)[number];

const CHIP = "px-2 py-0.5 rounded text-[10px] font-bold uppercase";

function when(sqlite: string): string {
  return sqlite.slice(0, 16).replace("T", " ");
}

/** Banks are the reason to look twice, so they say so; unknown never reads as none. */
function BanksChip({ banks }: { banks: string[] | null }) {
  if (banks === null) {
    return (
      <span
        title="Scanned before the hub kept this, so it may or may not have banks"
        className={`${CHIP} bg-yellow-500/15 text-yellow-400`}
      >
        Banks not recorded
      </span>
    );
  }
  if (banks.length === 0) return <span className="text-xs text-text-dim">No banks</span>;
  return (
    <span className={`${CHIP} bg-gold/15 text-gold`}>
      {banks.length} Wwise bank{banks.length === 1 ? "" : "s"}
    </span>
  );
}

function ReleaseCard({
  release: r,
  busy,
  onDecide,
}: {
  release: QueuedRelease;
  busy: boolean;
  onDecide: (action: "approve" | "reject", reason: string) => void;
}) {
  const [reason, setReason] = useState("");
  const why = reason.trim();
  // Every held release has this one; it's why the card exists, not news.
  const findings = r.findings.filter((f) => f.code !== "awaiting_review");

  return (
    <div className="rounded-lg border border-border p-4">
      <div className="flex flex-wrap items-center gap-2">
        {/* A draft or hidden mod's page 404s, even for a moderator. */}
        {r.mod_status === "published" ? (
          <Link href={`/mods/${r.mod_slug}`} className="text-sm font-semibold text-gold hover:underline">
            {r.mod_name}
          </Link>
        ) : (
          <span className="text-sm font-semibold text-foreground">{r.mod_name}</span>
        )}
        <span className="font-mono text-xs text-text-muted">v{r.version}</span>
        {r.mod_status === "draft" ? (
          <span className={`${CHIP} bg-surface-card text-text-muted`}>First release</span>
        ) : r.mod_status !== "published" ? (
          <span className={`${CHIP} bg-red-500/15 text-red-400`}>Mod {r.mod_status}</span>
        ) : null}
        <BanksChip banks={r.banks} />
      </div>

      <p className="text-xs text-text-dim mt-1">
        by <span className="text-text-muted">{r.uploader}</span> ·{" "}
        {r.file_size ? formatBytes(r.file_size) : "size unknown"}
        {r.map_code && (
          <>
            {" "}
            · map <span className="font-mono text-text-muted">{r.map_code}</span>
            {r.map_title && <> {r.map_title}</>}
          </>
        )}{" "}
        · held {when(r.created_at)}
      </p>

      {!!r.banks?.length && (
        <ul className="mt-2 rounded-md bg-surface-card px-3 py-2 font-mono text-[11px] text-text-muted">
          {r.banks.map((name) => (
            <li key={name} className="break-all">
              {name}
            </li>
          ))}
        </ul>
      )}

      {findings.length > 0 ? (
        <ul className="mt-2 space-y-1">
          {findings.map((f, i) => (
            <li key={i} className="flex items-start gap-2 text-xs">
              <AlertTriangle
                className={`w-3.5 h-3.5 mt-0.5 shrink-0 ${
                  f.level === "error" ? "text-red-400" : "text-yellow-400"
                }`}
              />
              <span className="text-text-muted min-w-0 break-words">
                <span className="font-mono text-text-dim">{f.code}</span> {f.message}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-xs text-text-dim">The scan found nothing to report.</p>
      )}

      {r.state === "pending" ? (
        <div className="flex flex-wrap gap-2 mt-3">
          <input
            type="text"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            maxLength={500}
            aria-label={`Reason for ${r.mod_name} v${r.version}`}
            placeholder="Reason (needed to reject; the author reads it)"
            className="flex-1 min-w-48 rounded-lg border border-border bg-surface-card px-3 py-1.5 text-xs text-foreground placeholder:text-text-dim focus:outline-none focus:border-gold"
          />
          <button
            onClick={() => onDecide("approve", why)}
            disabled={busy}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-green-500/15 text-green-400 hover:bg-green-500/25 disabled:opacity-40 transition-colors cursor-pointer"
          >
            <Check className="w-3.5 h-3.5" />
            Approve
          </button>
          <button
            onClick={() => onDecide("reject", why)}
            disabled={busy || !why}
            title={why ? undefined : "Give a reason first"}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-red-500/15 text-red-400 hover:bg-red-500/25 disabled:opacity-40 transition-colors cursor-pointer"
          >
            <X className="w-3.5 h-3.5" />
            Reject
          </button>
        </div>
      ) : (
        r.reason && <p className="mt-2 text-sm text-text-muted whitespace-pre-wrap">{r.reason}</p>
      )}
    </div>
  );
}

export function Releases({
  client,
  onError,
  onPending,
}: {
  client: HubClient;
  onError: (message: string | null) => void;
  /** How many are waiting, for the tab bar. */
  onPending: (count: number) => void;
}) {
  const [state, setState] = useState<State>("pending");
  const [releases, setReleases] = useState<QueuedRelease[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const fail = useCallback((e: unknown) => onError(e instanceof Error ? e.message : String(e)), [onError]);

  const load = useCallback(() => {
    client
      .listReleaseReviews(state)
      .then((rows) => {
        setReleases(rows);
        if (state === "pending") onPending(rows.length);
      })
      .catch(fail);
  }, [client, state, onPending, fail]);

  useEffect(load, [load]);

  const decide = async (r: QueuedRelease, action: "approve" | "reject", reason: string) => {
    setBusy(r.release_id);
    onError(null);
    try {
      await client.decideRelease(r.release_id, action, reason, r.sha256 ?? undefined);
    } catch (e) {
      fail(e);
    } finally {
      // After a refusal too: the card is out of date, whatever it says.
      load();
      setBusy(null);
    }
  };

  return (
    <section>
      <div className="flex flex-wrap items-center gap-3 mb-3">
        <h2 className="text-sm font-bold uppercase text-text-dim">
          Release review{releases ? ` · ${releases.length}` : ""}
        </h2>
        <div className="flex gap-1 ml-auto">
          {STATES.map((s) => (
            <button
              key={s}
              onClick={() => {
                if (s === state) return;
                setReleases(null);
                setState(s);
              }}
              className={`px-2.5 py-1 text-xs font-semibold rounded-lg capitalize transition-colors cursor-pointer ${
                s === state ? "bg-gold/15 text-gold" : "text-text-muted hover:text-foreground"
              }`}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      {releases === null ? (
        <p className="text-text-dim text-sm">Loading…</p>
      ) : releases.length === 0 ? (
        <p className="text-text-dim text-sm">
          {state === "pending" ? "Nothing is waiting for review." : `No ${state} releases.`}
        </p>
      ) : (
        <div className="space-y-4">
          {releases.map((r) => (
            <ReleaseCard
              key={r.release_id}
              release={r}
              busy={busy === r.release_id}
              onDecide={(action, reason) => void decide(r, action, reason)}
            />
          ))}
        </div>
      )}
    </section>
  );
}
