import { useCallback, useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { GAME_TYPE_NAMES, type Lobby, type MapListing } from "@mjolnir/hub-kit";
import { hubClient } from "../hub/client";
import type { Library } from "../hub/library";
import { MapTile, mapStatus } from "./hub/MapTile";

interface InstallProgress {
  stage: string;
  message: string;
  percent: number;
}

interface MultiplayerInstall {
  installed: string[];
  current: string[];
  failed: string[];
}

function humanSize(bytes: number): string {
  return `${(bytes / 1_048_576).toFixed(0)} MB`;
}

/**
 * The classic maps, and the one button that installs everything they need:
 * every official map pack, the CE runtime pack they share, and the code mods
 * that put MULTIPLAYER on the main menu (hub::install_multiplayer). Running
 * it again updates what moved on and skips the rest.
 *
 * Community maps are never part of that button: they install one at a time
 * from Browse Hub's Maps tab, or in game when a lobby needs one.
 */
export default function Multiplayer({
  library,
  onInstalled,
  onBrowseMaps,
  joinLobby,
  onJoinDismiss,
}: {
  library: Library;
  /** Lets the Updates tab drop what this run just installed. */
  onInstalled?: () => void;
  /** Browse Hub's Maps tab, where community maps are found. */
  onBrowseMaps?: () => void;
  /** A lobby id from a `mjolnir://join/<id>` link, to join now. */
  joinLobby?: string | null;
  onJoinDismiss?: () => void;
}) {
  const [maps, setMaps] = useState<MapListing[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState<InstallProgress | null>(null);
  const [result, setResult] = useState<MultiplayerInstall | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setMaps(await hubClient.listMaps({ official: true }));
      setLoadError(null);
    } catch (e) {
      setLoadError(String(e));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const stop = listen<InstallProgress>("install-progress", (event) => {
      if (event.payload.stage === "multiplayer") setProgress(event.payload);
    });
    return () => {
      void stop.then((unlisten) => unlisten());
    };
  }, []);

  // The state file is a record of what was installed, not proof it is still
  // on disk: a map whose files were deleted reads as not installed, so the
  // button offers it again (hub::missing_files).
  const [missingFiles, setMissingFiles] = useState<Set<string>>(new Set());
  useEffect(() => {
    invoke<string[]>("hub_missing_files").then(
      (slugs) => setMissingFiles(new Set(slugs)),
      () => setMissingFiles(new Set()),
    );
  }, [library.state]);

  const installedBySlug = new Map((library.state?.installed ?? []).map((m) => [m.slug, m]));
  const statusOf = (m: MapListing) =>
    mapStatus(m, installedBySlug.get(m.slug), missingFiles.has(m.slug));
  const missing = (maps ?? []).filter((m) => statusOf(m) !== "installed");
  const download = missing.reduce((sum, m) => sum + (m.release?.file_size ?? 0), 0);

  /** True when everything installed; the join panel waits on this. */
  async function installAll(): Promise<boolean> {
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const done = await invoke<MultiplayerInstall>("hub_install_multiplayer");
      setResult(done);
      return done.failed.length === 0;
    } catch (e) {
      setError(String(e));
      return false;
    } finally {
      setRunning(false);
      setProgress(null);
      await library.refresh();
      onInstalled?.();
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold">Multiplayer</h2>
          <p className="text-sm text-text-secondary mt-0.5">
            The classic Halo: Combat Evolved maps with Slayer, Capture the Flag and more, played
            with your fireteam. In game: MULTIPLAYER on the main menu.
          </p>
        </div>
        {onBrowseMaps && (
          <button
            onClick={onBrowseMaps}
            className="text-sm font-semibold text-mjolnir-gold hover:underline cursor-pointer"
          >
            Community maps →
          </button>
        )}
      </div>

      {joinLobby && (
        <JoinPanel
          lobby={joinLobby}
          installing={running}
          onInstallMultiplayer={installAll}
          onDismiss={() => onJoinDismiss?.()}
        />
      )}

      <div className="bg-surface-secondary border border-border-subtle rounded-xl p-4">
        <div className="flex items-center gap-4">
          <div className="flex-1 min-w-0">
            {maps === null ? (
              <p className="text-sm text-text-secondary">
                {loadError ? `Cannot reach the hub: ${loadError}` : "Checking the hub…"}
              </p>
            ) : missing.length === 0 ? (
              <p className="text-sm">All {maps.length} maps are installed and up to date.</p>
            ) : (
              <p className="text-sm">
                {missing.length} of {maps.length} maps to install or update
                {download ? ` · about ${humanSize(download)}` : ""}. The launcher also installs
                the shared CE runtime and the multiplayer mods.
              </p>
            )}
            {progress && (
              <div className="mt-2">
                <div className="h-1.5 rounded bg-surface-hover overflow-hidden">
                  <div
                    className="h-full bg-mjolnir-gold transition-all"
                    style={{ width: `${Math.round(progress.percent)}%` }}
                  />
                </div>
                <p className="text-xs text-text-secondary mt-1">{progress.message}</p>
              </div>
            )}
            {error && <p className="text-xs text-red-400 mt-1">{error}</p>}
            {result && (
              <p className="text-xs text-text-secondary mt-1">
                {result.installed.length} installed, {result.current.length} already current
                {result.failed.length ? `, ${result.failed.length} failed` : ""}.
              </p>
            )}
            {result?.failed.map((f) => (
              <p key={f} className="text-xs text-red-400 mt-0.5">
                {f}
              </p>
            ))}
          </div>
          <button
            onClick={() => void installAll()}
            disabled={running || maps === null || missing.length === 0}
            className="px-4 py-2 rounded-lg text-sm font-semibold shrink-0
              bg-gradient-to-r from-mjolnir-gold to-mjolnir-gold-dim text-surface-primary
              hover:brightness-110 disabled:opacity-50 cursor-pointer transition-all"
          >
            {running
              ? "Installing…"
              : maps && missing.length < maps.length && missing.length > 0
                ? "Update maps"
                : "Install multiplayer"}
          </button>
        </div>
      </div>

      {maps && maps.length > 0 && (
        <div className="grid grid-cols-2 xl:grid-cols-3 gap-3">
          {maps.map((m) => (
            <MapTile
              key={m.code}
              map={m}
              have={installedBySlug.get(m.slug)}
              status={statusOf(m)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/** What `hub_join_lobby` answers: whether it had to start the game. */
interface JoinStart {
  launched: boolean;
}

type JoinPhase =
  | { kind: "looking" }
  | { kind: "gone" }
  | { kind: "joining" }
  | { kind: "not-ready"; message: string }
  | { kind: "started"; launched: boolean }
  | { kind: "error"; message: string };

/**
 * A game picked on the website (`mjolnir://join/<id>`). The launcher only
 * hands it over: `hub_join_lobby` leaves the lobby id where MJOLNIR Lobby
 * looks for it and starts the game when it is not running; the game then
 * joins from the main menu through FIND GAMES, downloading the map first
 * when it has to, exactly as a join picked in game would.
 */
function JoinPanel({
  lobby,
  installing,
  onInstallMultiplayer,
  onDismiss,
}: {
  lobby: string;
  installing: boolean;
  onInstallMultiplayer: () => Promise<boolean>;
  onDismiss: () => void;
}) {
  const [game, setGame] = useState<Lobby | null>(null);
  const [phase, setPhase] = useState<JoinPhase>({ kind: "looking" });
  // One automatic hand-over per link: a second would start the game twice
  // (React runs effects twice in development, and the lookup may rerun).
  const handedOver = useRef<string | null>(null);

  const join = useCallback(async () => {
    setPhase({ kind: "joining" });
    try {
      const r = await invoke<JoinStart>("hub_join_lobby", { lobby });
      setPhase({ kind: "started", launched: r.launched });
    } catch (e) {
      const message = String(e);
      setPhase(
        message.startsWith("not_ready:")
          ? { kind: "not-ready", message: message.slice("not_ready:".length).trim() }
          : { kind: "error", message },
      );
    }
  }, [lobby]);

  // Look the game up first: a link can outlive its lobby, and starting the
  // game for one that has already ended only to be told so in game is worse
  // than saying it here. A hub that cannot be reached is no reason to stop,
  // the game checks again anyway.
  useEffect(() => {
    let live = true;
    setGame(null);
    setPhase({ kind: "looking" });
    hubClient.listLobbies().then(
      (lobbies) => {
        if (!live) return;
        const found = lobbies.find((l) => l.id === lobby) ?? null;
        setGame(found);
        if (!found) setPhase({ kind: "gone" });
        else if (handedOver.current !== lobby) {
          handedOver.current = lobby;
          void join();
        }
      },
      () => {
        if (!live || handedOver.current === lobby) return;
        handedOver.current = lobby;
        void join();
      },
    );
    return () => {
      live = false;
    };
  }, [lobby, join]);

  const who = game ? `${game.host}'s game` : "the game";
  const line = (() => {
    switch (phase.kind) {
      case "looking":
        return "Looking up the game…";
      case "gone":
        return "That game has ended or is no longer listed.";
      case "joining":
        return `Handing ${who} to Halo…`;
      case "not-ready":
        return phase.message || "Multiplayer is not installed yet.";
      case "started":
        return phase.launched
          ? `Starting Halo. Press start at the title screen and it joins ${who} from the main menu.`
          : `Halo is already running: switch to it and it joins ${who} from the main menu.`;
      case "error":
        return `Could not join: ${phase.message}`;
    }
  })();

  return (
    <div className="bg-surface-secondary border border-mjolnir-gold/40 rounded-xl p-4">
      <div className="flex items-start gap-4">
        <div className="flex-1 min-w-0">
          <p className="text-xs uppercase tracking-wide text-mjolnir-gold">Join from the website</p>
          {game ? (
            <p className="font-semibold mt-1 truncate">
              {game.name}
              <span className="font-normal text-text-secondary">
                {" "}
                · {game.map_title ?? game.map_code} · {GAME_TYPE_NAMES[game.game_type] ?? game.game_type} ·{" "}
                {game.players}/{game.max_players}
              </span>
            </p>
          ) : null}
          <p
            className={`text-sm mt-1 ${
              phase.kind === "error" || phase.kind === "gone" ? "text-red-400" : "text-text-secondary"
            }`}
          >
            {line}
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {phase.kind === "not-ready" && (
            <button
              onClick={() =>
                void onInstallMultiplayer().then((ok) => {
                  if (ok) void join();
                })
              }
              disabled={installing}
              className="px-3 py-1.5 rounded-lg text-sm font-semibold
                bg-gradient-to-r from-mjolnir-gold to-mjolnir-gold-dim text-surface-primary
                hover:brightness-110 disabled:opacity-50 cursor-pointer transition-all"
            >
              {installing ? "Installing…" : "Install multiplayer and join"}
            </button>
          )}
          {phase.kind === "error" && (
            <button
              onClick={() => void join()}
              className="px-3 py-1.5 rounded-lg text-sm border border-border-subtle hover:border-mjolnir-gold/40 cursor-pointer"
            >
              Try again
            </button>
          )}
          <button
            onClick={onDismiss}
            className="px-3 py-1.5 rounded-lg text-sm text-text-secondary hover:text-text-primary cursor-pointer"
          >
            {phase.kind === "started" ? "Done" : "Dismiss"}
          </button>
        </div>
      </div>
    </div>
  );
}
