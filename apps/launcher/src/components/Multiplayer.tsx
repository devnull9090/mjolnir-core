import { useCallback, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { GAME_TYPE_NAMES, type MapListing } from "@mjolnir/hub-kit";
import { HUB_SITE, hubClient } from "../hub/client";
import type { Library } from "../hub/library";

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
 */
export default function Multiplayer({ library }: { library: Library }) {
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

  const installedBySlug = new Map(
    (library.state?.installed ?? [])
      .filter((m) => !missingFiles.has(m.slug))
      .map((m) => [m.slug, m]),
  );
  const missing = (maps ?? []).filter((m) => {
    const have = installedBySlug.get(m.slug);
    return !have || (m.release && have.release_id !== m.release.id);
  });
  const download = missing.reduce((sum, m) => sum + (m.release?.file_size ?? 0), 0);

  async function installAll() {
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      setResult(await invoke<MultiplayerInstall>("hub_install_multiplayer"));
    } catch (e) {
      setError(String(e));
    } finally {
      setRunning(false);
      setProgress(null);
      await library.refresh();
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-xl font-bold">Multiplayer</h2>
        <p className="text-sm text-text-secondary mt-0.5">
          The classic Halo: Combat Evolved maps with Slayer, Capture the Flag and more, played
          with your fireteam. In game: MULTIPLAYER on the main menu.
        </p>
      </div>

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
          {maps.map((m) => {
            const have = installedBySlug.get(m.slug);
            const current = have && (!m.release || have.release_id === m.release.id);
            return (
              <div
                key={m.code}
                className="bg-surface-secondary border border-border-subtle rounded-xl overflow-hidden"
              >
                {m.cover_url ? (
                  <img
                    src={`${HUB_SITE}${m.cover_url}`}
                    alt={m.title}
                    loading="lazy"
                    className="w-full aspect-video object-cover bg-surface-hover"
                  />
                ) : (
                  <div className="w-full aspect-video bg-surface-hover" />
                )}
                <div className="p-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-semibold truncate">{m.title}</span>
                  <span
                    className={`text-[11px] px-1.5 py-0.5 rounded ${
                      current
                        ? "bg-emerald-500/15 text-emerald-400"
                        : have
                          ? "bg-mjolnir-gold/15 text-mjolnir-gold"
                          : "bg-surface-hover text-text-secondary"
                    }`}
                  >
                    {current ? "Installed" : have ? "Update" : "Not installed"}
                  </span>
                </div>
                <p className="text-xs text-text-secondary mt-1">
                  {m.modes.map((mode) => GAME_TYPE_NAMES[mode] ?? mode).join(" · ")}
                </p>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
