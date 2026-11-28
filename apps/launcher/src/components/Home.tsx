/**
 * Home — the launcher's live command deck.
 *
 * Brings together local install status, one-click Play, live public lobbies,
 * recent match reports, and the newest community mods from mjolnircore.com
 * without leaving the launcher.
 */
import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import {
  ActionButton,
  Avatar,
  Badge,
  DownloadIcon,
  RefreshIcon,
  Stars,
  formatCount,
  timeAgo,
  useHub,
  GAME_TYPE_NAMES,
  type Lobby,
  type MatchSummary,
  type Mod,
} from "@mjolnir/hub-kit";

import { HUB_SITE } from "../hub/client";
import type { Library } from "../hub/library";
import type { HubPulse } from "../hub/useHubPulse";
import { usePreflight } from "../launch/preflight";
import type { InstallStatus } from "./GameLocation";
import { isHaloCeMap } from "./hub/MapTile";

const HERO_IMAGE = `${HUB_SITE}/api/v1/media/a5f46d72-16af-4e0e-866d-226645d19df1`;

function formatDuration(ms: number): string {
  const totalSec = Math.max(0, Math.round(ms / 1000));
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function resolveMedia(url: string | null): string | null {
  if (!url) return null;
  return url.startsWith("/") ? `${HUB_SITE}${url}` : url;
}

export default function Home({
  library,
  pulse,
  updateCount,
  onOpenMod,
  onJoinLobby,
  onGoToMods,
  onGoToMultiplayer,
  onGoToBrowse,
  onGoToUpdates,
}: {
  library: Library;
  pulse: HubPulse;
  updateCount: number;
  onOpenMod: (slug: string) => void;
  onJoinLobby: (lobbyId: string) => void;
  onGoToMods: () => void;
  onGoToMultiplayer: () => void;
  onGoToBrowse: () => void;
  onGoToUpdates: () => void;
}) {
  const { user, openUrl } = useHub();
  const preflight = usePreflight();
  const [installStatus, setInstallStatus] = useState<InstallStatus | null>(null);

  useEffect(() => {
    invoke<InstallStatus>("get_install_status")
      .then(setInstallStatus)
      .catch(() => setInstallStatus(null));
  }, [library.state]);

  const installedSlugs = new Set((library.state?.installed ?? []).map((m) => m.slug));
  const ceMaps = pulse.maps.filter((m) => m.official && isHaloCeMap(m));
  const installedCeMaps = ceMaps.filter((m) => installedSlugs.has(m.slug)).length;
  const activeProfile = library.state?.profiles.find((p) => p.name === library.state?.active);
  const enabledModsCount = activeProfile?.entries.filter((e) => e.enabled).length ?? 0;

  const needsSetup = installStatus !== null && (!installStatus.game_found || !installStatus.ue4ss_installed);
  const greetingName = user?.display_name ?? user?.username ?? null;

  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      {/* ── Cinematic Hero Command Deck ──────────────────────────────── */}
      <section className="launcher-hud-corners relative isolate overflow-hidden rounded-2xl border border-border-subtle bg-surface-secondary shadow-[0_24px_56px_-28px_rgba(0,0,0,0.9)]">
        <img
          src={HERO_IMAGE}
          alt=""
          className="launcher-hero-drift absolute inset-0 -z-20 h-full w-full object-cover object-center opacity-55"
        />
        <div
          aria-hidden="true"
          className="absolute inset-0 -z-10 bg-gradient-to-r from-[#070a12f5] via-[#070a12d6] to-[#070a1268]"
        />
        <div
          aria-hidden="true"
          className="absolute inset-0 -z-10 bg-gradient-to-t from-[#070a12] via-transparent to-[#070a1240]"
        />

        <div className="p-6 sm:p-7 flex flex-col gap-5">
          {/* Status rail */}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2">
              {pulse.lobbies.length > 0 ? (
                <button
                  type="button"
                  onClick={onGoToMultiplayer}
                  className="inline-flex items-center gap-2 rounded-full border border-accent-green/35 bg-accent-green/12 px-3 py-1 font-mono text-[11px] font-semibold uppercase tracking-wider text-accent-green hover:bg-accent-green/20 transition-colors cursor-pointer"
                >
                  <span className="relative flex h-2 w-2 items-center justify-center" aria-hidden="true">
                    <span className="launcher-live-ring absolute inline-flex h-full w-full rounded-full bg-accent-green" />
                    <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-accent-green" />
                  </span>
                  {pulse.lobbies.length} live game{pulse.lobbies.length === 1 ? "" : "s"} ·{" "}
                  {pulse.livePlayers} online
                </button>
              ) : (
                <span className="inline-flex items-center gap-2 rounded-full border border-mjolnir-gold/30 bg-surface-primary/70 px-3 py-1 font-mono text-[10px] font-semibold uppercase tracking-[0.16em] text-mjolnir-gold backdrop-blur-sm">
                  <span className="h-1.5 w-1.5 rounded-full bg-mjolnir-gold" />
                  MJOLNIR Command Deck
                </span>
              )}

              {updateCount > 0 && (
                <button
                  type="button"
                  onClick={onGoToUpdates}
                  className="inline-flex items-center gap-1.5 rounded-full border border-mjolnir-gold/40 bg-mjolnir-gold/15 px-3 py-1 text-[11px] font-semibold text-mjolnir-gold hover:bg-mjolnir-gold/25 transition-colors cursor-pointer"
                >
                  {updateCount} update{updateCount === 1 ? "" : "s"} ready →
                </button>
              )}
            </div>

            <button
              type="button"
              onClick={() => void pulse.refresh()}
              disabled={pulse.refreshing}
              className="inline-flex items-center gap-1.5 rounded-lg border border-border-subtle/80 bg-surface-primary/60 px-2.5 py-1 text-xs text-text-secondary hover:border-mjolnir-gold/40 hover:text-text-primary backdrop-blur-sm transition-colors cursor-pointer disabled:opacity-50"
              title="Refresh live games, recent matches, and latest mods"
            >
              <RefreshIcon className={`w-3.5 h-3.5 ${pulse.refreshing ? "animate-spin" : ""}`} />
              {pulse.refreshing ? "Refreshing…" : "Refresh"}
            </button>
          </div>

          {/* Headline & primary CTAs */}
          <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-6">
            <div className="max-w-xl">
              <h2 className="text-2xl sm:text-3xl font-black tracking-tight text-white leading-tight">
                {greetingName ? (
                  <>
                    Welcome back, <span className="text-mjolnir-gold">{greetingName}</span>.
                  </>
                ) : (
                  <>
                    Halo Campaign Evolved, <span className="text-mjolnir-gold">ready to drop.</span>
                  </>
                )}
              </h2>
              <p className="mt-2 text-sm text-text-secondary leading-relaxed">
                {needsSetup
                  ? "Finish installing the MJOLNIR modding framework in My Mods to unlock classic maps, multiplayer lobbies, and community content."
                  : "Launch straight into multiplayer, jump into a live public lobby, or inspect the latest community releases on the hub."}
              </p>

              {/* Quick install telemetry */}
              <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-text-secondary">
                {ceMaps.length > 0 && (
                  <button
                    type="button"
                    onClick={onGoToMultiplayer}
                    className="inline-flex items-center gap-1.5 hover:text-text-primary cursor-pointer"
                  >
                    <span
                      className={`h-2 w-2 rounded-full ${
                        installedCeMaps >= ceMaps.length ? "bg-accent-green" : "bg-mjolnir-gold"
                      }`}
                    />
                    <span className="tabular-nums">
                      {installedCeMaps}/{ceMaps.length} classic CE maps
                    </span>
                  </button>
                )}
                <button
                  type="button"
                  onClick={onGoToMods}
                  className="inline-flex items-center gap-1.5 hover:text-text-primary cursor-pointer"
                >
                  <span className="h-2 w-2 rounded-full bg-accent-blue" />
                  <span className="tabular-nums">
                    {enabledModsCount} active content mod{enabledModsCount === 1 ? "" : "s"}
                  </span>
                </button>
                {installStatus?.ue4ss_installed && (
                  <span className="inline-flex items-center gap-1.5">
                    <span
                      className={`h-2 w-2 rounded-full ${
                        installStatus.modpack_enabled ? "bg-accent-green" : "bg-accent-red"
                      }`}
                    />
                    UE4SS {installStatus.modpack_enabled ? "Active" : "Paused"}
                  </span>
                )}
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2.5 shrink-0">
              {needsSetup ? (
                <button
                  type="button"
                  onClick={onGoToMods}
                  className="launcher-sheen inline-flex items-center gap-2 rounded-xl px-5 py-3 text-sm font-bold tracking-wide uppercase bg-gradient-to-r from-[#e5bc57] via-mjolnir-gold to-mjolnir-gold-dim text-surface-primary hover:brightness-110 active:scale-[0.98] transition-all cursor-pointer shadow-lg shadow-mjolnir-gold/25"
                >
                  Finish Setup →
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() =>
                    preflight.run({ launch: () => invoke("launch_game") }).catch(console.error)
                  }
                  className="launcher-sheen inline-flex items-center gap-2.5 rounded-xl px-5 py-3 text-sm font-bold tracking-wide uppercase bg-gradient-to-r from-[#e5bc57] via-mjolnir-gold to-mjolnir-gold-dim text-surface-primary hover:brightness-110 active:scale-[0.98] transition-all cursor-pointer shadow-lg shadow-mjolnir-gold/25"
                >
                  <svg className="w-4 h-4 fill-current" viewBox="0 0 24 24" aria-hidden="true">
                    <path d="M8 5v14l11-7z" />
                  </svg>
                  Launch Game
                </button>
              )}
              <button
                type="button"
                onClick={onGoToMultiplayer}
                className="inline-flex items-center gap-2 rounded-xl border border-white/15 bg-surface-primary/70 px-4 py-3 text-sm font-semibold text-text-primary backdrop-blur-sm hover:border-mjolnir-gold/50 hover:text-mjolnir-gold transition-all cursor-pointer"
              >
                Multiplayer
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* ── Live Public Games Strip ──────────────────────────────────── */}
      <section className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span
              className={`h-2 w-2 rounded-full ${
                pulse.lobbies.length > 0 ? "bg-accent-green animate-pulse" : "bg-text-secondary/50"
              }`}
            />
            <h3 className="text-xs font-bold uppercase tracking-[0.14em] text-text-secondary">
              Live multiplayer games
            </h3>
            {pulse.lobbies.length > 0 && (
              <Badge tone="green">
                {pulse.lobbies.length} open · {pulse.livePlayers} playing
              </Badge>
            )}
          </div>
          <div className="flex items-center gap-3 text-xs">
            <button
              type="button"
              onClick={() => openUrl(`${HUB_SITE}/games`)}
              className="text-text-secondary hover:text-text-primary cursor-pointer"
            >
              Web browser ↗
            </button>
            <button
              type="button"
              onClick={onGoToMultiplayer}
              className="font-semibold text-mjolnir-gold hover:underline cursor-pointer"
            >
              Manage maps →
            </button>
          </div>
        </div>

        {pulse.loading ? (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            {[0, 1].map((i) => (
              <div key={i} className="launcher-skeleton h-24 rounded-xl border border-border-subtle" />
            ))}
          </div>
        ) : pulse.lobbies.length > 0 ? (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            {pulse.lobbies.slice(0, 4).map((lobby) => (
              <LiveLobbyCard
                key={lobby.id}
                lobby={lobby}
                coverUrl={resolveMedia(pulse.coversByCode.get(lobby.map_code) ?? null)}
                onJoin={() => onJoinLobby(lobby.id)}
              />
            ))}
          </div>
        ) : (
          <div className="rounded-xl border border-dashed border-border-subtle bg-surface-secondary/50 px-5 py-4 flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="text-sm font-medium text-text-primary">No public lobbies listed right now</p>
              <p className="text-xs text-text-secondary mt-0.5">
                Launch Halo, open MULTIPLAYER, and set a lobby to PUBLIC GAME — it appears here and on mjolnircore.com immediately.
              </p>
            </div>
            <ActionButton size="sm" tone="gold" onClick={onGoToMultiplayer}>
              Open Multiplayer
            </ActionButton>
          </div>
        )}
      </section>

      {/* ── Two-Column Live Hub Feed: Recent Matches + Latest Mods ──── */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        {/* Recent Public Matches */}
        <section className="space-y-3 min-w-0">
          <div className="flex items-center justify-between gap-3">
            <h3 className="text-xs font-bold uppercase tracking-[0.14em] text-text-secondary">
              Recent public matches
            </h3>
            <button
              type="button"
              onClick={() => openUrl(`${HUB_SITE}/matches`)}
              className="text-xs font-semibold text-mjolnir-gold hover:underline cursor-pointer"
            >
              Match history &amp; 3D replays ↗
            </button>
          </div>

          {pulse.loading ? (
            <div className="space-y-2.5">
              {[0, 1, 2].map((i) => (
                <div key={i} className="launcher-skeleton h-20 rounded-xl border border-border-subtle" />
              ))}
            </div>
          ) : pulse.matches.length > 0 ? (
            <div className="space-y-2.5">
              {pulse.matches.map((match) => (
                <RecentMatchRow
                  key={match.id}
                  match={match}
                  onOpen={() => openUrl(`${HUB_SITE}/matches/${match.id}`)}
                />
              ))}
            </div>
          ) : (
            <div className="rounded-xl border border-dashed border-border-subtle bg-surface-secondary/40 p-6 text-center text-xs text-text-secondary">
              {pulse.error
                ? "Offline — connect to the hub to view recent match reports."
                : "Recent public matches appear here once games finish."}
            </div>
          )}
        </section>

        {/* Latest Community Mods */}
        <section className="space-y-3 min-w-0">
          <div className="flex items-center justify-between gap-3">
            <h3 className="text-xs font-bold uppercase tracking-[0.14em] text-text-secondary">
              Latest community mods
            </h3>
            <button
              type="button"
              onClick={onGoToBrowse}
              className="text-xs font-semibold text-mjolnir-gold hover:underline cursor-pointer"
            >
              Browse Hub →
            </button>
          </div>

          {pulse.loading ? (
            <div className="space-y-2.5">
              {[0, 1, 2].map((i) => (
                <div key={i} className="launcher-skeleton h-20 rounded-xl border border-border-subtle" />
              ))}
            </div>
          ) : pulse.latestMods.length > 0 ? (
            <div className="space-y-2.5">
              {pulse.latestMods.map((mod) => (
                <LatestModRow
                  key={mod.id}
                  mod={mod}
                  installed={installedSlugs.has(mod.slug)}
                  onOpen={() => onOpenMod(mod.slug)}
                />
              ))}
            </div>
          ) : (
            <div className="rounded-xl border border-dashed border-border-subtle bg-surface-secondary/40 p-6 text-center text-xs text-text-secondary">
              {pulse.error
                ? "Offline — your installed mods continue working normally."
                : "Community mods published on the hub appear here."}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

export function LiveLobbyCard({
  lobby,
  coverUrl,
  onJoin,
}: {
  lobby: Lobby;
  coverUrl: string | null;
  onJoin: () => void;
}) {
  const full = lobby.state === "full" || lobby.players >= lobby.max_players;
  const fill = Math.min(100, Math.round((lobby.players / Math.max(1, lobby.max_players)) * 100));

  return (
    <article className="group launcher-card flex overflow-hidden rounded-xl border border-border-subtle bg-surface-secondary hover:border-mjolnir-gold/45">
      <div className="relative w-28 shrink-0 bg-surface-card overflow-hidden">
        {coverUrl ? (
          <img
            src={coverUrl}
            alt=""
            loading="lazy"
            className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center bg-gradient-to-br from-surface-card to-surface-primary">
            <span className="font-mono text-sm font-bold tracking-widest text-text-secondary/50">
              {lobby.map_code}
            </span>
          </div>
        )}
      </div>

      <div className="flex flex-1 min-w-0 flex-col gap-2 p-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <h4 className="truncate text-sm font-bold text-text-primary">{lobby.name}</h4>
            <p className="truncate text-xs text-text-secondary">
              {lobby.map_title ?? lobby.map_code} ·{" "}
              {GAME_TYPE_NAMES[lobby.game_type] ?? lobby.game_type}
            </p>
          </div>
          {lobby.state === "in_game" ? (
            <Badge tone="gold">In game</Badge>
          ) : (
            <Badge tone="green">Open</Badge>
          )}
        </div>

        <div className="mt-auto flex items-end justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2.5 text-[11px] text-text-secondary tabular-nums">
              <span className="font-semibold text-text-primary">
                {lobby.players}/{lobby.max_players} players
              </span>
              {lobby.ping_ms !== null && <span>~{lobby.ping_ms} ms</span>}
              <span className="truncate">by {lobby.host}</span>
            </div>
            <div className="mt-1.5 h-1 w-full max-w-36 overflow-hidden rounded-full bg-surface-hover">
              <div
                className={`h-full rounded-full ${full ? "bg-text-secondary" : "bg-mjolnir-gold"}`}
                style={{ width: `${fill}%` }}
              />
            </div>
          </div>
          <ActionButton size="sm" tone="gold" disabled={full} onClick={onJoin}>
            {full ? "Full" : "Join"}
          </ActionButton>
        </div>
      </div>
    </article>
  );
}

function RecentMatchRow({ match, onOpen }: { match: MatchSummary; onOpen: () => void }) {
  const cover = resolveMedia(match.map_cover_url);
  const mode = GAME_TYPE_NAMES[match.game_type] ?? match.game_type;
  const winnerSeat = match.podium.find((p) => p.outcome === "win");
  const isTeam = match.team_game && match.red_score !== null && match.blue_score !== null;
  const totalTeamScore = (match.red_score ?? 0) + (match.blue_score ?? 0);
  const redPct = totalTeamScore === 0 ? 50 : Math.round(((match.red_score ?? 0) / totalTeamScore) * 100);

  return (
    <button
      type="button"
      onClick={onOpen}
      className="group launcher-card w-full text-left flex items-center gap-3.5 rounded-xl border border-border-subtle bg-surface-secondary p-2.5 hover:border-mjolnir-gold/45 cursor-pointer"
    >
      <div className="relative h-16 w-24 shrink-0 overflow-hidden rounded-lg border border-border-subtle/70 bg-surface-card">
        {cover ? (
          <img
            src={cover}
            alt=""
            loading="lazy"
            className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center font-mono text-xs font-bold text-text-secondary/50">
            {match.map_code}
          </div>
        )}
        <span className="absolute bottom-1 right-1 rounded bg-surface-primary/85 px-1 py-0.5 font-mono text-[10px] text-text-secondary tabular-nums">
          {formatDuration(match.duration_ms)}
        </span>
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2">
          <p className="truncate text-sm font-bold text-text-primary group-hover:text-mjolnir-gold transition-colors">
            {match.map_title ?? match.map_code}
          </p>
          <span className="shrink-0 text-[11px] text-text-secondary">
            {timeAgo(match.ended_at.replace(" ", "T") + "Z")}
          </span>
        </div>

        <p className="mt-0.5 text-xs text-text-secondary">
          {mode} · {match.player_count} players
        </p>

        {isTeam ? (
          <div className="mt-1.5 flex items-center gap-2 text-[11px] font-bold tabular-nums">
            <span className="text-red-400">RED {match.red_score}</span>
            <div className="flex h-1.5 flex-1 max-w-28 overflow-hidden rounded-full bg-surface-hover">
              <span className="bg-red-400" style={{ width: `${redPct}%` }} />
              <span className="bg-sky-400 flex-1" />
            </div>
            <span className="text-sky-400">{match.blue_score} BLUE</span>
          </div>
        ) : winnerSeat ? (
          <p className="mt-1 text-xs text-text-secondary truncate">
            <span className="text-mjolnir-gold font-semibold">Winner:</span> {winnerSeat.name}{" "}
            <span className="tabular-nums text-text-secondary/80">({winnerSeat.score})</span>
          </p>
        ) : (
          <p className="mt-1 text-xs text-text-secondary truncate">
            {match.end_reason === "abandoned" ? "Ended early" : "Draw"} · Hosted by {match.host}
          </p>
        )}
      </div>

      <span
        aria-hidden="true"
        className="pr-1 text-xs text-text-secondary group-hover:text-mjolnir-gold transition-colors shrink-0"
      >
        ↗
      </span>
    </button>
  );
}

function LatestModRow({
  mod,
  installed,
  onOpen,
}: {
  mod: Mod;
  installed: boolean;
  onOpen: () => void;
}) {
  const cover = resolveMedia(mod.cover_url);
  return (
    <button
      type="button"
      onClick={onOpen}
      className="group launcher-card w-full text-left flex items-center gap-3.5 rounded-xl border border-border-subtle bg-surface-secondary p-2.5 hover:border-mjolnir-gold/45 cursor-pointer"
    >
      <div className="relative h-16 w-24 shrink-0 overflow-hidden rounded-lg border border-border-subtle/70 bg-surface-card">
        {cover ? (
          <img
            src={cover}
            alt=""
            loading="lazy"
            className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center font-mono text-[10px] uppercase tracking-wider text-text-secondary/60">
            {mod.category}
          </div>
        )}
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="truncate text-sm font-bold text-text-primary group-hover:text-mjolnir-gold transition-colors">
            {mod.name}
          </span>
          <Badge>{mod.category}</Badge>
          {installed && <Badge tone="green">installed</Badge>}
        </div>
        <p className="mt-0.5 truncate text-xs text-text-secondary">
          {mod.summary ?? "No summary."}
        </p>
        <div className="mt-1.5 flex items-center gap-3 text-[11px] text-text-secondary">
          <span className="inline-flex items-center gap-1 min-w-0">
            <Avatar url={mod.author_avatar} size="xs" />
            <span className="truncate">{mod.author}</span>
          </span>
          <span className="inline-flex items-center gap-1 tabular-nums">
            <DownloadIcon className="w-3 h-3" />
            {formatCount(mod.download_count)}
          </span>
          <Stars value={mod.rating_mean} count={mod.rating_count} />
        </div>
      </div>

      <span
        aria-hidden="true"
        className="pr-1 text-xs text-text-secondary group-hover:translate-x-0.5 group-hover:text-mjolnir-gold transition-all shrink-0"
      >
        →
      </span>
    </button>
  );
}
