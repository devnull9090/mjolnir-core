import { useState, useEffect, useCallback } from "react";
import { invoke } from "@tauri-apps/api/core";
import SetupPanel from "./SetupPanel";

interface ModEntry {
  name: string;
  enabled: boolean;
  description: string;
  version: string;
}

interface InstallStatus {
  game_found: boolean;
  install_path: string | null;
  platform: string;
  ue4ss_installed: boolean;
  modpack_enabled: boolean;
  manifest_version: string | null;
  ue4ss_version: string | null;
}

export default function ModList() {
  const [mods, setMods] = useState<ModEntry[]>([]);
  const [installStatus, setInstallStatus] = useState<InstallStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [toggling, setToggling] = useState(false);

  const loadData = useCallback(async () => {
    try {
      const status = await invoke<InstallStatus>("get_install_status");
      setInstallStatus(status);

      if (status.ue4ss_installed) {
        const modList = await invoke<ModEntry[]>("get_mods");
        setMods(modList);
      }
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

  const toggleModpack = async () => {
    if (!installStatus || toggling) return;
    setToggling(true);
    try {
      const newState = await invoke<boolean>("set_modpack_enabled", {
        enabled: !installStatus.modpack_enabled,
      });
      setInstallStatus((prev) =>
        prev ? { ...prev, modpack_enabled: newState } : prev
      );
    } catch (err) {
      console.error("Failed to toggle modpack:", err);
    } finally {
      setToggling(false);
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

  // Show setup panel if game not found or UE4SS not installed
  if (installStatus && (!installStatus.game_found || !installStatus.ue4ss_installed)) {
    return (
      <SetupPanel
        installStatus={installStatus}
        onInstallComplete={() => {
          setLoading(true);
          loadData();
        }}
      />
    );
  }

  return (
    <div>
      {/* Header with master toggle */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <h2 className="text-xl font-bold text-text-primary">Installed Mods</h2>

            {/* Master modpack toggle */}
            {installStatus && (
              <button
                onClick={toggleModpack}
                disabled={toggling}
                title={installStatus.modpack_enabled ? "Disable all mods (UE4SS)" : "Enable all mods (UE4SS)"}
                className={`relative w-11 h-6 rounded-full transition-colors duration-200 cursor-pointer flex-shrink-0
                  ${installStatus.modpack_enabled ? "bg-accent-green" : "bg-accent-red/60"}`}
              >
                <span
                  className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow-md transition-transform duration-200
                    ${installStatus.modpack_enabled ? "translate-x-5" : "translate-x-0"}`}
                />
              </button>
            )}

            {installStatus && (
              <span
                className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                  installStatus.modpack_enabled
                    ? "bg-accent-green/15 text-accent-green"
                    : "bg-accent-red/15 text-accent-red"
                }`}
              >
                {installStatus.modpack_enabled ? "UE4SS Active" : "UE4SS Disabled"}
              </span>
            )}
          </div>

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

      {/* Disabled overlay notice */}
      {installStatus && !installStatus.modpack_enabled && (
        <div className="mb-4 p-3 rounded-xl bg-accent-red/8 border border-accent-red/20 text-sm flex items-center gap-3">
          <svg className="w-5 h-5 text-accent-red flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
          </svg>
          <div>
            <p className="font-medium text-accent-red">Modding is disabled</p>
            <p className="text-text-secondary text-xs mt-0.5">
              UE4SS is currently disabled. The game will run without any mods. Toggle the switch above to re-enable.
            </p>
          </div>
        </div>
      )}

      {/* Mod list */}
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
