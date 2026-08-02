/**
 * My Mods — everything installed on this machine, in one place.
 *
 * Previously "installed" meant two different screens: this one listed the
 * UE4SS script mods in mods.txt, while the Hub tab listed the content mods
 * it had downloaded, and neither mentioned the other. A player with a
 * texture pack and a script mod had no single answer to "what am I running?"
 *
 * Now the split is by *what you do*, not by where it came from: this view
 * manages what is installed, Browse Hub finds new things, and Updates
 * upgrades them. The two kinds of mod stay visibly distinct — one is game
 * data ordered by load order, the other is code toggled through UE4SS — but
 * they live under one heading.
 */
import { useCallback, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { ActionButton, Badge, ErrorNote, ShieldIcon, Spinner } from "@mjolnir/hub-kit";

import SetupPanel from "./SetupPanel";
import { InstalledPanel } from "./hub/InstalledPanel";
import type { Library as HubLibrary } from "../hub/library";

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

type Integrity = "not_installed" | "verified" | "modified" | "unverified";

interface CodeModRow {
  id: string;
  version: string;
  summary: string;
  installed_version: string | null;
  update_available: boolean;
  integrity: Integrity;
}

interface CodeModsStatus {
  set_version: string;
  signature_verified: boolean;
  mods: CodeModRow[];
}

/**
 * What the launcher is willing to say about a mod's bytes.
 *
 * Being named after a signed mod is not the same as being one, so `signed`
 * is spent only where the installed tree still hashes to what was extracted.
 * The other three states each say something different and none of them is
 * an accusation: a modpack-shipped mod is `unverified` because this launcher
 * never installed it, not because anything is wrong with it.
 */
function TrustBadge({ integrity }: { integrity?: Integrity }) {
  switch (integrity) {
    case "verified":
      return (
        <Badge tone="blue" title="Installed from the Ed25519-signed set, and the files on disk still match what was installed.">
          <ShieldIcon className="w-3 h-3" />
          signed
        </Badge>
      );
    case "modified":
      return (
        <Badge tone="red" title="This mod is in the signed set, but its files have changed since the launcher installed them. Reinstall it from Browse Hub to get the signed copy back.">
          modified
        </Badge>
      );
    case "unverified":
      return (
        <Badge tone="amber" title="In the signed set and present on disk, but the launcher has no record of installing it — it came with the modpack, or predates content verification. Reinstall from Browse Hub to verify it.">
          unverified
        </Badge>
      );
    default:
      return (
        <Badge tone="amber" title="Found in ue4ss/Mods but not part of the signed set — the launcher did not install it and cannot vouch for it.">
          unmanaged
        </Badge>
      );
  }
}

export default function Library({
  library,
  updateCount,
  onOpenMod,
  onGoToUpdates,
  onGoToBrowse,
}: {
  library: HubLibrary;
  /** The manager's total, so the launcher never shows two update counts. */
  updateCount: number;
  onOpenMod: (slug: string) => void;
  onGoToUpdates: () => void;
  onGoToBrowse: () => void;
}) {
  const [status, setStatus] = useState<InstallStatus | null>(null);
  const [scripts, setScripts] = useState<ModEntry[]>([]);
  const [signed, setSigned] = useState<CodeModsStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [toggling, setToggling] = useState(false);

  const load = useCallback(async () => {
    try {
      const s = await invoke<InstallStatus>("get_install_status");
      setStatus(s);
      if (s.ue4ss_installed) {
        setScripts(await invoke<ModEntry[]>("get_mods"));
        // Only used to annotate rows; a hub that is down must not empty the
        // list of what is installed.
        invoke<CodeModsStatus>("code_mods_status").then(setSigned).catch(() => setSigned(null));
      }
    } catch (err) {
      console.error("Failed to load the library:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const toggleScript = async (name: string, enabled: boolean) => {
    try {
      await invoke("toggle_mod", { name, enabled });
      setScripts((prev) => prev.map((m) => (m.name === name ? { ...m, enabled } : m)));
    } catch (err) {
      console.error("Failed to toggle mod:", err);
    }
  };

  const toggleModpack = async () => {
    if (!status || toggling) return;
    setToggling(true);
    try {
      const next = await invoke<boolean>("set_modpack_enabled", {
        enabled: !status.modpack_enabled,
      });
      setStatus((prev) => (prev ? { ...prev, modpack_enabled: next } : prev));
    } catch (err) {
      console.error("Failed to toggle the modpack:", err);
    } finally {
      setToggling(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spinner className="w-6 h-6" />
      </div>
    );
  }

  if (status && (!status.game_found || !status.ue4ss_installed)) {
    return (
      <SetupPanel
        installStatus={status}
        onInstallComplete={() => {
          setLoading(true);
          void load();
        }}
      />
    );
  }

  const contentCount =
    library.state?.profiles.find((p) => p.name === library.state?.active)?.entries.length ?? 0;
  const setById = new Map(signed?.mods.map((m) => [m.id, m]) ?? []);

  return (
    <div className="space-y-8">
      {/* ── What is running at all ── */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <h2 className="text-xl font-bold">My Mods</h2>
          {status && (
            <>
              <button
                onClick={toggleModpack}
                disabled={toggling}
                title={status.modpack_enabled ? "Disable all mods (UE4SS)" : "Enable all mods (UE4SS)"}
                className={`relative w-11 h-6 rounded-full transition-colors duration-200 cursor-pointer shrink-0
                  ${status.modpack_enabled ? "bg-accent-green" : "bg-accent-red/60"}`}
              >
                <span
                  className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow-md transition-transform duration-200
                    ${status.modpack_enabled ? "translate-x-5" : "translate-x-0"}`}
                />
              </button>
              <span
                className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                  status.modpack_enabled
                    ? "bg-accent-green/15 text-accent-green"
                    : "bg-accent-red/15 text-accent-red"
                }`}
              >
                {status.modpack_enabled ? "UE4SS Active" : "UE4SS Disabled"}
              </span>
            </>
          )}
        </div>

        <div className="flex items-center gap-2">
          {updateCount > 0 && (
            <ActionButton size="sm" onClick={onGoToUpdates}>
              {updateCount} update{updateCount === 1 ? "" : "s"} available
            </ActionButton>
          )}
          <ActionButton size="sm" tone="neutral" onClick={onGoToBrowse}>
            Find more mods
          </ActionButton>
        </div>
      </div>

      {status && !status.modpack_enabled && (
        <div className="p-3 rounded-xl bg-accent-red/8 border border-accent-red/20 text-sm">
          <p className="font-medium text-accent-red">Modding is disabled</p>
          <p className="text-text-secondary text-xs mt-0.5">
            UE4SS is switched off, so the game will run unmodded — including the content mods
            below. Toggle the switch above to re-enable.
          </p>
        </div>
      )}

      {/* ── Content mods: game data, ordered ── */}
      <section>
        <InstalledPanel library={library} onSelect={onOpenMod} onGoToUpdates={onGoToUpdates} />
      </section>

      {/* ── Script mods: code, toggled ── */}
      <section>
        <div className="mb-3">
          <h3 className="text-lg font-bold">Script mods</h3>
          <p className="text-sm text-text-secondary mt-0.5">
            UE4SS Lua running inside the game. {scripts.length === 0
              ? "None found in ue4ss/Mods."
              : `${scripts.filter((m) => m.enabled).length} of ${scripts.length} enabled.`}
          </p>
        </div>

        {library.error && <ErrorNote>{library.error}</ErrorNote>}

        <div className="space-y-2">
          {scripts.map((mod) => {
            const fromSet = setById.get(mod.name);
            return (
              <div
                key={mod.name}
                className={`flex items-center gap-4 p-4 rounded-xl border transition-all duration-200
                  ${
                    mod.enabled
                      ? "bg-surface-card border-border-subtle"
                      : "bg-surface-primary border-border-subtle/50 opacity-60"
                  }`}
              >
                <button
                  onClick={() => toggleScript(mod.name, !mod.enabled)}
                  aria-label={`${mod.enabled ? "Disable" : "Enable"} ${mod.name}`}
                  className={`relative w-11 h-6 rounded-full transition-colors duration-200 cursor-pointer shrink-0
                    ${mod.enabled ? "bg-accent-green" : "bg-surface-hover"}`}
                >
                  <span
                    className={`absolute top-0.5 left-0.5 w-5 h-5 bg-white rounded-full shadow-md transition-transform duration-200
                      ${mod.enabled ? "translate-x-5" : "translate-x-0"}`}
                  />
                </button>

                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-semibold text-sm">{mod.name}</span>
                    <Badge>v{fromSet?.installed_version || mod.version}</Badge>
                    <TrustBadge integrity={fromSet?.integrity} />
                    {fromSet?.update_available && (
                      <Badge tone="gold">v{fromSet.version} available</Badge>
                    )}
                  </div>
                  <p className="text-xs text-text-secondary mt-0.5 truncate">
                    {fromSet?.summary || mod.description}
                  </p>
                </div>

                {fromSet?.update_available && (
                  <ActionButton size="sm" onClick={onGoToUpdates}>
                    Update
                  </ActionButton>
                )}
              </div>
            );
          })}

          {scripts.length === 0 && (
            <p className="text-sm text-text-secondary border border-dashed border-border-subtle rounded-xl p-6 text-center">
              No script mods installed — the signed set is on the Browse Hub tab.
            </p>
          )}
        </div>
      </section>

      {contentCount === 0 && scripts.length === 0 && (
        <p className="text-sm text-text-secondary text-center">
          Nothing installed yet.{" "}
          <button onClick={onGoToBrowse} className="text-mjolnir-gold hover:underline cursor-pointer">
            Browse the hub
          </button>{" "}
          to get started.
        </p>
      )}
    </div>
  );
}
