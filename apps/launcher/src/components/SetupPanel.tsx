import { useState, useEffect } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen, UnlistenFn } from "@tauri-apps/api/event";
import GameLocation, { type InstallStatus } from "./GameLocation";

interface InstallProgress {
  stage: string;
  message: string;
  percent: number;
}

interface CodeModRow {
  id: string;
  summary: string;
  default: boolean;
}

/** Fixed part of the bundle. The mods after it come from the signed set. */
const RUNTIME_ITEMS = [
  { name: "UE4SS v3.0.1", desc: "Unreal Engine scripting framework" },
  { name: "AOB Signatures", desc: "HCE-specific memory patterns" },
];

interface SetupPanelProps {
  installStatus: InstallStatus;
  onInstallComplete: () => void;
}

export default function SetupPanel({ installStatus, onInstallComplete }: SetupPanelProps) {
  const [installing, setInstalling] = useState(false);
  const [progress, setProgress] = useState<InstallProgress | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const [defaults, setDefaults] = useState<CodeModRow[] | null>(null);

  // What setup installs is a question the signed set answers, so ask it rather
  // than keeping a second copy here. This list used to be hardcoded, and named
  // five mods that setup had stopped installing entirely.
  useEffect(() => {
    invoke<{ mods: CodeModRow[] }>("code_mods_status")
      .then((s) => setDefaults(s.mods.filter((m) => m.default)))
      .catch(() => setDefaults(null));
  }, []);

  useEffect(() => {
    let unlisten: UnlistenFn | null = null;

    listen<InstallProgress>("install-progress", (event) => {
      setProgress(event.payload);
      if (event.payload.stage === "done") {
        setDone(true);
        setInstalling(false);
      }
    }).then((fn) => {
      unlisten = fn;
    });

    return () => {
      if (unlisten) unlisten();
    };
  }, []);

  const handleInstall = async () => {
    setInstalling(true);
    setError(null);
    setDone(false);
    setProgress({ stage: "downloading", message: "Starting installation...", percent: 0 });

    try {
      await invoke("install_modpack");
      // Progress events will handle the UI updates
      setTimeout(() => onInstallComplete(), 1500);
    } catch (err) {
      setError(String(err));
      setInstalling(false);
    }
  };

  if (!installStatus.game_found) {
    return (
      <div className="flex flex-col items-center h-full overflow-y-auto text-center px-8 py-10">
        <div className="w-20 h-20 rounded-2xl bg-accent-red/10 border border-accent-red/30 flex items-center justify-center mb-6">
          <svg className="w-10 h-10 text-accent-red" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4.5c-.77-.833-2.694-.833-3.464 0L3.34 16.5c-.77.833.192 2.5 1.732 2.5z" />
          </svg>
        </div>
        <h2 className="text-xl font-bold text-text-primary mb-2">Game Not Found</h2>
        <p className="text-sm text-text-secondary max-w-md mb-6">
          Could not detect <strong>Halo Campaign Evolved</strong> in any of the usual places.
          If it is installed somewhere else — another drive, a moved folder — point MJOLNIR
          at it below. Otherwise install it first, then relaunch MJOLNIR.
        </p>
        <a
          href="https://store.steampowered.com/app/2806050/Halo_Campaign_Evolved/"
          target="_blank"
          rel="noopener noreferrer"
          className="px-5 py-2.5 rounded-lg text-sm font-medium bg-accent-blue/15 border border-accent-blue/30 text-accent-blue
            hover:bg-accent-blue/25 transition-all duration-150 mb-8"
        >
          View on Steam →
        </a>

        {/* The way out of the dead end this screen used to be. */}
        <div className="w-full max-w-xl border-t border-border-subtle pt-8">
          <GameLocation onChanged={(status) => status.game_found && onInstallComplete()} />
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center h-full text-center px-8">
      {/* Icon */}
      <div className="w-20 h-20 rounded-2xl bg-mjolnir-gold/10 border border-mjolnir-gold/30 flex items-center justify-center mb-6">
        <svg className="w-10 h-10 text-mjolnir-gold" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
        </svg>
      </div>

      {/* Title */}
      <h2 className="text-xl font-bold text-text-primary mb-2">Set Up MJOLNIR Mods</h2>
      <p className="text-sm text-text-secondary max-w-lg mb-2">
        UE4SS and MJOLNIR mods are not installed yet. Click below to download and install
        the modding framework — UE4SS, the signature overrides tuned for this game, and the
        mods a MJOLNIR install needs to do anything.
      </p>

      {installStatus.install_path && (
        <p className="text-xs text-text-secondary mb-6 font-mono opacity-60">
          Target: {installStatus.install_path}\Meteorite\Binaries\Win64\
        </p>
      )}

      {/* Progress bar */}
      {(installing || done) && progress && (
        <div className="w-full max-w-md mb-6">
          {/* Bar */}
          <div className="w-full h-2.5 rounded-full bg-surface-hover overflow-hidden mb-2">
            <div
              className={`h-full rounded-full transition-all duration-300 ease-out ${
                done ? "bg-accent-green" : "bg-gradient-to-r from-mjolnir-gold to-mjolnir-gold-dim"
              }`}
              style={{ width: `${Math.min(progress.percent, 100)}%` }}
            />
          </div>

          {/* Stage label */}
          <div className="flex items-center justify-between text-xs">
            <span className="text-text-secondary truncate max-w-[80%]">{progress.message}</span>
            <span className={`font-semibold ${done ? "text-accent-green" : "text-mjolnir-gold"}`}>
              {Math.round(progress.percent)}%
            </span>
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="w-full max-w-md mb-6 p-3 rounded-xl bg-accent-red/10 border border-accent-red/30 text-sm text-left">
          <p className="font-semibold text-accent-red mb-1">Installation Failed</p>
          <p className="text-text-secondary text-xs break-all">{error}</p>
        </div>
      )}

      {/* Install button */}
      {!installing && !done && (
        <button
          onClick={handleInstall}
          className="px-8 py-3 rounded-xl text-sm font-bold tracking-wide uppercase
            bg-gradient-to-r from-mjolnir-gold to-mjolnir-gold-dim text-surface-primary
            hover:brightness-110 active:brightness-90
            transition-all duration-150 cursor-pointer
            shadow-lg shadow-mjolnir-gold/20"
        >
          ⬇ Install MJOLNIR Mods
        </button>
      )}

      {/* Done message */}
      {done && (
        <div className="flex items-center gap-2 text-accent-green font-semibold text-sm">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
          </svg>
          Installation complete! Loading mods...
        </div>
      )}

      {/* What gets installed */}
      {!installing && !done && (
        <div className="mt-8 w-full max-w-md text-left">
          <p className="text-xs text-text-secondary uppercase tracking-wider mb-3 font-semibold">
            What gets installed
          </p>
          <div className="space-y-2">
            {[
              ...RUNTIME_ITEMS,
              ...(defaults ?? []).map((m) => ({ name: m.id, desc: m.summary })),
            ].map((item) => (
              <div
                key={item.name}
                className="flex items-center gap-3 p-2.5 rounded-lg bg-surface-card/50 border border-border-subtle/50"
              >
                <div className="w-1.5 h-1.5 rounded-full bg-mjolnir-gold flex-shrink-0" />
                <div>
                  <span className="text-xs font-medium text-text-primary">{item.name}</span>
                  <span className="text-xs text-text-secondary ml-2">{item.desc}</span>
                </div>
              </div>
            ))}
          </div>
          <p className="text-xs text-text-secondary mt-3">
            Everything else in the signed set — the developer, diagnostic and experimental
            mods — is left off. You can install any of it from My Mods afterwards.
          </p>
        </div>
      )}
    </div>
  );
}
