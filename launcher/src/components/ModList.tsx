import { useState, useEffect, useCallback } from "react";
import { invoke } from "@tauri-apps/api/core";

interface ModEntry {
  name: string;
  enabled: boolean;
  description: string;
  version: string;
}

interface GameInfo {
  found: boolean;
  install_path: string | null;
  ue4ss_installed: boolean;
  mods_path: string | null;
}

export default function ModList() {
  const [mods, setMods] = useState<ModEntry[]>([]);
  const [gameInfo, setGameInfo] = useState<GameInfo | null>(null);
  const [loading, setLoading] = useState(true);

  const loadData = useCallback(async () => {
    try {
      const [info, modList] = await Promise.all([
        invoke<GameInfo>("detect_game"),
        invoke<ModEntry[]>("get_mods"),
      ]);
      setGameInfo(info);
      setMods(modList);
    } catch (err) {
      console.error("Failed to load data:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const toggleMod = async (name: string, enabled: boolean) => {
    try {
      await invoke("toggle_mod", { name, enabled });
      setMods((prev) =>
        prev.map((m) => (m.name === name ? { ...m, enabled } : m))
      );
    } catch (err) {
      console.error("Failed to toggle mod:", err);
    }
  };

  const enabledCount = mods.filter((m) => m.enabled).length;

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="w-6 h-6 border-2 border-mjolnir-gold border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <div>
      {/* Game Status */}
      {gameInfo && !gameInfo.found && (
        <div className="mb-6 p-4 rounded-xl bg-accent-red/10 border border-accent-red/30 text-sm">
          <p className="font-semibold text-accent-red">Game Not Found</p>
          <p className="text-text-secondary mt-1">
            Could not detect Halo Campaign Evolved. Please install it via Steam.
          </p>
        </div>
      )}

      {gameInfo && gameInfo.found && !gameInfo.ue4ss_installed && (
        <div className="mb-6 p-4 rounded-xl bg-mjolnir-gold/10 border border-mjolnir-gold/30 text-sm">
          <p className="font-semibold text-mjolnir-gold">UE4SS Not Installed</p>
          <p className="text-text-secondary mt-1">
            UE4SS was not found at{" "}
            <code className="text-xs bg-surface-hover px-1 py-0.5 rounded">
              {gameInfo.install_path}\Meteorite\Binaries\Win64\ue4ss\
            </code>
          </p>
        </div>
      )}

      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-bold text-text-primary">Installed Mods</h2>
          <p className="text-sm text-text-secondary mt-1">
            {mods.length > 0
              ? `${enabledCount} of ${mods.length} mods enabled`
              : "No mods detected — install mods into ue4ss/Mods/"}
          </p>
        </div>
        <button className="px-4 py-2 text-sm font-medium rounded-lg bg-surface-card border border-border-subtle text-text-secondary hover:text-text-primary hover:border-mjolnir-gold/40 transition-all duration-150 cursor-pointer">
          + Install from file
        </button>
      </div>

      <div className="space-y-2">
        {mods.map((mod) => (
          <div
            key={mod.name}
            className={`group flex items-center gap-4 p-4 rounded-xl border transition-all duration-200
              ${
                mod.enabled
                  ? "bg-surface-card border-border-subtle hover:border-mjolnir-gold/30"
                  : "bg-surface-primary border-border-subtle/50 opacity-60 hover:opacity-80"
              }`}
          >
            {/* Toggle */}
            <button
              onClick={() => toggleMod(mod.name, !mod.enabled)}
              className={`relative w-11 h-6 rounded-full transition-colors duration-200 cursor-pointer flex-shrink-0
                ${mod.enabled ? "bg-accent-green" : "bg-surface-hover"}`}
            >
              <span
                className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow-md transition-transform duration-200
                  ${mod.enabled ? "translate-x-5" : "translate-x-0"}`}
              />
            </button>

            {/* Info */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="font-semibold text-sm text-text-primary">{mod.name}</span>
                <span className="text-[10px] text-text-secondary px-1.5 py-0.5 rounded bg-surface-hover">
                  v{mod.version}
                </span>
              </div>
              <p className="text-xs text-text-secondary mt-0.5 truncate">{mod.description}</p>
            </div>

            {/* Actions */}
            <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity duration-150">
              <button className="p-1.5 rounded-md text-text-secondary hover:text-accent-blue hover:bg-surface-hover transition-colors cursor-pointer" title="More options">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 6.75a.75.75 0 110-1.5.75.75 0 010 1.5zM12 12.75a.75.75 0 110-1.5.75.75 0 010 1.5zM12 18.75a.75.75 0 110-1.5.75.75 0 010 1.5z" />
                </svg>
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
