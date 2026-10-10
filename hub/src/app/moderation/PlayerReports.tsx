"use client";

/**
 * Player reports from multiplayer, grouped by the player reported, and the
 * matchmaking bans in force (docs/player_identity.md).
 *
 * A moderator reads every report against someone at once, with the match
 * each was filed from and whether the hub has both players in it, then
 * upholds or dismisses each and, if it comes to that, bans the player from
 * matchmaking for a while or for good. Dismissed reports leave the public
 * count on the player's profile; upheld ones stay in it.
 */
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Ban, Check, X } from "lucide-react";

import type { BannedPlayer, HubClient, PlayerReportReason, ReportedPlayer } from "@mjolnir/hub-kit";

const REASONS: Record<PlayerReportReason, string> = {
  cheating: "Cheating",
  betraying: "Betraying",
  harassment: "Harassment",
  griefing: "Griefing / AFK",
  quitting: "Quitting",
  name: "Name or avatar",
  other: "Other",
};

const DURATIONS: [string, number | undefined][] = [
  ["1 day", 1],
  ["3 days", 3],
  ["7 days", 7],
  ["30 days", 30],
  ["Permanent", undefined],
];

const STATUSES = ["open", "upheld", "dismissed"] as const;
type Status = (typeof STATUSES)[number];

function when(sqlite: string | null): string {
  return sqlite ? sqlite.slice(0, 16).replace("T", " ") : "";
}

function until(expires: string | null): string {
  return expires ? `until ${when(expires)} UTC` : "permanently";
}

function PlayerAvatar({ url }: { url: string | null }) {
  return url ? (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={url} alt="" className="w-9 h-9 rounded-full border border-border" />
  ) : (
    <div className="w-9 h-9 rounded-full border border-border bg-surface-card" />
  );
}

function BanForm({
  busy,
  onBan,
}: {
  busy: boolean;
  onBan: (reason: string, days: number | undefined) => void;
}) {
  const [reason, setReason] = useState("");
  const [duration, setDuration] = useState(2);
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (reason.trim()) onBan(reason.trim(), DURATIONS[duration][1]);
      }}
      className="flex flex-wrap gap-2 mt-3"
    >
      <input
        type="text"
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        maxLength={500}
        placeholder="Why (the player sees this)"
        className="flex-1 min-w-48 rounded-lg border border-border bg-surface-card px-3 py-1.5 text-xs text-foreground placeholder:text-text-dim focus:outline-none focus:border-gold"
      />
      <select
        value={duration}
        onChange={(e) => setDuration(Number(e.target.value))}
        className="rounded-lg border border-border bg-surface-card px-2 py-1.5 text-xs text-foreground"
      >
        {DURATIONS.map(([label], i) => (
          <option key={label} value={i}>
            {label}
          </option>
        ))}
      </select>
      <button
        type="submit"
        disabled={busy || !reason.trim()}
        className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-red-500/15 text-red-400 hover:bg-red-500/25 disabled:opacity-40 transition-colors cursor-pointer"
      >
        <Ban className="w-3.5 h-3.5" />
        Ban from matchmaking
      </button>
    </form>
  );
}

export function PlayerReports({
  client,
  onError,
}: {
  client: HubClient;
  onError: (message: string | null) => void;
}) {
  const [status, setStatus] = useState<Status>("open");
  const [players, setPlayers] = useState<ReportedPlayer[] | null>(null);
  const [bans, setBans] = useState<BannedPlayer[] | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const fail = useCallback((e: unknown) => onError(e instanceof Error ? e.message : String(e)), [onError]);

  const load = useCallback(() => {
    client.listPlayerReports(status).then(setPlayers).catch(fail);
    client.listMatchmakingBans().then(setBans).catch(fail);
  }, [client, status, fail]);

  useEffect(load, [load]);

  const act = async (key: string, run: () => Promise<unknown>) => {
    setBusy(key);
    onError(null);
    try {
      await run();
      load();
    } catch (e) {
      fail(e);
    } finally {
      setBusy(null);
    }
  };

  return (
    <>
      <section className="mb-12">
        <div className="flex flex-wrap items-center gap-3 mb-3">
          <h2 className="text-sm font-bold uppercase text-text-dim">
            Player reports{players ? ` · ${players.length}` : ""}
          </h2>
          <div className="flex gap-1 ml-auto">
            {STATUSES.map((s) => (
              <button
                key={s}
                onClick={() => {
                  if (s === status) return;
                  setPlayers(null);
                  setStatus(s);
                }}
                className={`px-2.5 py-1 text-xs font-semibold rounded-lg capitalize transition-colors cursor-pointer ${
                  s === status ? "bg-gold/15 text-gold" : "text-text-muted hover:text-foreground"
                }`}
              >
                {s}
              </button>
            ))}
          </div>
        </div>

        {players === null ? (
          <p className="text-text-dim text-sm">Loading…</p>
        ) : players.length === 0 ? (
          <p className="text-text-dim text-sm">
            {status === "open" ? "No players reported." : `No ${status} reports.`}
          </p>
        ) : (
          <div className="space-y-4">
            {players.map((p) => (
              <div key={p.player.id} className="rounded-lg border border-border p-4">
                <div className="flex flex-wrap items-center gap-3">
                  <PlayerAvatar url={p.player.avatar_url} />
                  <div className="min-w-0">
                    <Link
                      href={`/users/${p.player.id}`}
                      className="text-sm font-semibold text-gold hover:underline"
                    >
                      {p.player.name}
                    </Link>
                    <p className="text-xs text-text-dim">
                      @{p.player.username} · {p.open_reports} open · {p.counted_reports} public
                    </p>
                  </div>
                  {p.ban && (
                    <span
                      title={p.ban.reason}
                      className="ml-auto px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-red-500/15 text-red-400"
                    >
                      Banned {until(p.ban.expires_at)}
                    </span>
                  )}
                </div>

                <div className="mt-3 space-y-2">
                  {p.reports.map((r) => (
                    <div key={r.id} className="rounded-md bg-surface-card px-3 py-2">
                      <div className="flex flex-wrap items-center gap-2 text-xs">
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-red-500/15 text-red-400">
                          {REASONS[r.reason] ?? r.reason}
                        </span>
                        <span className="text-text-dim">
                          by{" "}
                          <Link href={`/users/${r.reporter.id}`} className="text-text-muted hover:underline">
                            {r.reporter.name}
                          </Link>{" "}
                          · {when(r.created_at)}
                          {r.subject_name && <> · seen as “{r.subject_name}”</>}
                        </span>
                        {r.match_id ? (
                          <Link href={`/matches/${r.match_id}`} className="text-gold hover:underline">
                            match
                            {r.reporter_in_match === false || r.subject_in_match === false
                              ? " (a player is not linked to it)"
                              : ""}
                          </Link>
                        ) : r.host_match_id ? (
                          <span className="text-text-dim">match not on the hub</span>
                        ) : null}
                        {r.status !== "open" && (
                          <span className="text-text-dim">
                            · {r.status} by {r.decided_by ?? "?"} {when(r.decided_at)}
                            {r.decision_note && <> — {r.decision_note}</>}
                          </span>
                        )}
                        {r.status === "open" && (
                          <span className="ml-auto flex gap-1.5">
                            <button
                              onClick={() => act(r.id, () => client.decidePlayerReport(r.id, "uphold"))}
                              disabled={busy === r.id}
                              title="Agree with it; it stays in the public count"
                              className="flex items-center gap-1 px-2 py-1 text-[11px] font-semibold rounded-lg bg-green-500/15 text-green-400 hover:bg-green-500/25 disabled:opacity-40 transition-colors cursor-pointer"
                            >
                              <Check className="w-3 h-3" />
                              Uphold
                            </button>
                            <button
                              onClick={() => act(r.id, () => client.decidePlayerReport(r.id, "dismiss"))}
                              disabled={busy === r.id}
                              title="Unfounded; it leaves the public count"
                              className="flex items-center gap-1 px-2 py-1 text-[11px] font-semibold rounded-lg bg-surface text-text-muted hover:text-foreground disabled:opacity-40 transition-colors cursor-pointer"
                            >
                              <X className="w-3 h-3" />
                              Dismiss
                            </button>
                          </span>
                        )}
                      </div>
                      {r.detail && <p className="text-sm text-text-muted mt-1.5 whitespace-pre-wrap">{r.detail}</p>}
                    </div>
                  ))}
                </div>

                {p.ban ? (
                  <button
                    onClick={() => act(p.player.id, () => client.liftMatchmakingBan(p.player.id))}
                    disabled={busy === p.player.id}
                    className="mt-3 px-3 py-1.5 text-xs font-semibold rounded-lg bg-surface-card text-text-muted hover:text-foreground disabled:opacity-40 transition-colors cursor-pointer"
                  >
                    Lift ban
                  </button>
                ) : (
                  <BanForm
                    busy={busy === p.player.id}
                    onBan={(reason, days) =>
                      act(p.player.id, () => client.banFromMatchmaking(p.player.id, reason, days))
                    }
                  />
                )}
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="mb-12">
        <h2 className="text-sm font-bold uppercase text-text-dim mb-3">
          Matchmaking bans{bans ? ` · ${bans.length}` : ""}
        </h2>
        {bans === null ? (
          <p className="text-text-dim text-sm">Loading…</p>
        ) : bans.length === 0 ? (
          <p className="text-text-dim text-sm">Nobody is banned.</p>
        ) : (
          <div className="space-y-2">
            {bans.map((b) => (
              <div key={b.id} className="rounded-lg border border-border p-3 flex flex-wrap items-center gap-3">
                <PlayerAvatar url={b.player.avatar_url} />
                <div className="min-w-0 flex-1">
                  <Link href={`/users/${b.player.id}`} className="text-sm font-semibold text-gold hover:underline">
                    {b.player.name}
                  </Link>
                  <p className="text-xs text-text-dim">
                    {until(b.expires_at)} · by {b.banned_by ?? "?"} on {when(b.created_at)} — {b.reason}
                  </p>
                </div>
                <button
                  onClick={() => act(b.player.id, () => client.liftMatchmakingBan(b.player.id))}
                  disabled={busy === b.player.id}
                  className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-surface-card text-text-muted hover:text-foreground disabled:opacity-40 transition-colors cursor-pointer"
                >
                  Lift
                </button>
              </div>
            ))}
          </div>
        )}
      </section>
    </>
  );
}
