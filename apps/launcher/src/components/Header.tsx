import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import AccountChip from "./AccountChip";

/**
 * Both pills used to be hardcoded, so they kept claiming a version the build
 * had long since left behind. They read the real thing now: the launcher
 * version from the binary, the UE4SS version from the installed manifest.
 */
export default function Header({
  liveLobbies = 0,
  livePlayers = 0,
  onOpenMultiplayer,
}: {
  liveLobbies?: number;
  livePlayers?: number;
  onOpenMultiplayer?: () => void;
}) {
  const [launcherVersion, setLauncherVersion] = useState<string | null>(null);
  const [ue4ssVersion, setUe4ssVersion] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      const [build, install] = await Promise.allSettled([
        invoke<{ launcher_version: string }>("get_build_info"),
        invoke<{ ue4ss_installed: boolean; ue4ss_version: string | null }>(
          "get_install_status",
        ),
      ]);
      if (build.status === "fulfilled") setLauncherVersion(build.value.launcher_version);
      // Nothing installed, or installed before the manifest recorded a
      // version — either way there is no number to show, so show no pill.
      if (install.status === "fulfilled" && install.value.ue4ss_installed) {
        setUe4ssVersion(install.value.ue4ss_version);
      }
    })();
  }, []);

  return (
    <header className="h-14 shrink-0 bg-surface-secondary/85 backdrop-blur-md border-b border-border-subtle flex items-center justify-between gap-4 px-6">
      {/* Versions sit with the game name, so the right side is live status + account. */}
      <div className="flex items-center gap-2.5 min-w-0">
        <span className="w-2 h-2 rounded-full bg-accent-green animate-pulse shrink-0" />
        <span className="text-sm font-medium text-text-primary whitespace-nowrap">
          Halo Campaign Evolved
        </span>
        {launcherVersion && (
          <span className="rounded-md border border-mjolnir-gold/30 bg-mjolnir-gold/10 px-2 py-0.5 font-mono text-[11px] text-mjolnir-gold font-semibold whitespace-nowrap">
            v{launcherVersion}
          </span>
        )}
        {ue4ssVersion && (
          <span
            title={`UE4SS v${ue4ssVersion}`}
            className="hidden sm:inline-block rounded-md border border-border-subtle bg-surface-primary/60 px-2 py-0.5 font-mono text-[11px] text-text-secondary truncate"
          >
            UE4SS v{ue4ssVersion}
          </span>
        )}
      </div>

      <div className="flex items-center gap-3 shrink-0">
        {liveLobbies > 0 && onOpenMultiplayer && (
          <button
            type="button"
            onClick={onOpenMultiplayer}
            className="hidden md:inline-flex items-center gap-2 rounded-full border border-accent-green/30 bg-accent-green/10 px-3 py-1 text-xs font-semibold text-accent-green hover:bg-accent-green/20 transition-colors cursor-pointer tabular-nums"
            title="Jump to live public multiplayer games"
          >
            <span className="h-1.5 w-1.5 rounded-full bg-accent-green animate-pulse" />
            {liveLobbies} live · {livePlayers} online
          </button>
        )}
        <AccountChip />
      </div>
    </header>
  );
}
