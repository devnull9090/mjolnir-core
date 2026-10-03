import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import AccountChip from "./AccountChip";

/**
 * Both pills used to be hardcoded, so they kept claiming a version the build
 * had long since left behind. They read the real thing now: the launcher
 * version from the binary, the UE4SS version from the installed manifest.
 */
export default function Header() {
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
    <header className="h-14 bg-surface-secondary/80 backdrop-blur-sm border-b border-border-subtle flex items-center justify-between px-6">
      {/* Versions sit with the game name, so the right side is the account alone. */}
      <div className="flex items-center gap-3 min-w-0">
        <div className="w-2 h-2 rounded-full bg-accent-green animate-pulse shrink-0" />
        <span className="text-sm text-text-secondary whitespace-nowrap">
          Halo Campaign Evolved
        </span>
        {launcherVersion && (
          <span className="text-xs text-mjolnir-gold font-semibold whitespace-nowrap">
            MJOLNIR v{launcherVersion}
          </span>
        )}
        {ue4ssVersion && (
          <span
            title={`UE4SS v${ue4ssVersion}`}
            className="text-xs text-text-secondary/70 truncate"
          >
            UE4SS v{ue4ssVersion}
          </span>
        )}
      </div>
      <AccountChip />
    </header>
  );
}
