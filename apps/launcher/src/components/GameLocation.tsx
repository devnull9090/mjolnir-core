import { useCallback, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { open } from "@tauri-apps/plugin-dialog";

export interface InstallStatus {
  game_found: boolean;
  install_path: string | null;
  platform: string;
  ue4ss_installed: boolean;
  modpack_enabled: boolean;
  manifest_version: string | null;
  ue4ss_version: string | null;
  /** "manual" | "env" | "auto" | "none" */
  source: string;
  manual_path: string | null;
}

interface InstallPathCheck {
  valid: boolean;
  resolved: string | null;
  ue4ss_installed: boolean;
  message: string;
}

/** How the current path was arrived at, in the player's terms. */
const SOURCE_LABEL: Record<string, string> = {
  manual: "Set by you",
  env: "From MJOLNIR_GAME_DIR",
  auto: "Detected automatically",
  none: "Not found",
};

/**
 * Where the game is, when detection cannot work it out.
 *
 * Detection only knows the conventional store layouts, so a library on an
 * unusual drive or a copy that has been moved leaves the launcher with nothing
 * to install into. This is the way out of that, and it is the same panel in
 * Settings and on the "game not found" screen — one place to learn, whichever
 * of the two a player hits first.
 */
export default function GameLocation({
  onChanged,
}: {
  /** Fired after the location changes, so the surrounding view can reload. */
  onChanged?: (status: InstallStatus) => void;
}) {
  const [status, setStatus] = useState<InstallStatus | null>(null);
  const [candidate, setCandidate] = useState("");
  const [check, setCheck] = useState<InstallPathCheck | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setStatus(await invoke<InstallStatus>("get_install_status"));
    } catch (err) {
      setError(String(err));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  /** Check as soon as there is something to check, so "Use this folder" is
   *  never the first thing to say no. */
  const inspect = useCallback(async (path: string) => {
    const trimmed = path.trim();
    if (!trimmed) {
      setCheck(null);
      return;
    }
    try {
      setCheck(await invoke<InstallPathCheck>("check_install_path", { path: trimmed }));
    } catch (err) {
      setError(String(err));
    }
  }, []);

  const handleBrowse = async () => {
    try {
      const selected = await open({ directory: true, multiple: false });
      if (typeof selected === "string") {
        setCandidate(selected);
        void inspect(selected);
      }
    } catch (err) {
      setError(String(err));
    }
  };

  const apply = async (path: string | null) => {
    setBusy(true);
    setError(null);
    try {
      const next = await invoke<InstallStatus>("set_install_path", { path });
      setStatus(next);
      setCandidate("");
      setCheck(null);
      onChanged?.(next);
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  };

  const source = status?.source ?? "none";
  // A location that was set and has since gone — an unplugged drive, a moved
  // folder — is the one case worth naming outright, because "not found" reads
  // as "search again" and searching will not find it.
  const brokenManual = status !== null && !status.game_found && status.manual_path !== null;

  return (
    <section className="w-full">
      <h3 className="text-sm font-semibold text-text-primary uppercase tracking-wider mb-4 flex items-center gap-2">
        <svg className="w-4 h-4 text-mjolnir-gold" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
        </svg>
        Game Location
      </h3>

      {/* Where things stand */}
      <div className="rounded-xl border border-border-subtle bg-surface-card p-4 mb-4 text-left">
        <div className="flex items-center justify-between gap-3 mb-1">
          <span className="text-xs text-text-secondary">Install folder</span>
          <span
            className={`text-[11px] px-2 py-0.5 rounded-full border ${
              status?.game_found
                ? "text-accent-green border-accent-green/30 bg-accent-green/10"
                : "text-accent-red border-accent-red/30 bg-accent-red/10"
            }`}
          >
            {SOURCE_LABEL[source] ?? source}
          </span>
        </div>
        <p className="font-mono text-xs text-text-primary break-all">
          {status?.install_path ?? status?.manual_path ?? "Not found"}
        </p>

        {brokenManual && (
          <p className="mt-3 text-xs text-accent-red">
            That folder is not there any more, or no longer holds the game. Pick it again
            below, or go back to detecting it automatically.
          </p>
        )}

        {source === "env" && (
          <p className="mt-3 text-xs text-text-secondary">
            Set by the <code className="bg-surface-hover px-1 py-0.5 rounded">MJOLNIR_GAME_DIR</code>{" "}
            environment variable. Choosing a folder here overrides it.
          </p>
        )}

        {status?.source === "manual" && (
          <button
            onClick={() => void apply(null)}
            disabled={busy}
            className="mt-3 text-xs text-text-secondary hover:text-mjolnir-gold disabled:opacity-50
              transition-colors duration-150 cursor-pointer underline underline-offset-2"
          >
            Detect automatically instead
          </button>
        )}
      </div>

      {/* Choosing a new one */}
      <label className="block text-xs text-text-secondary mb-1.5">
        Choose the folder holding the game
      </label>
      <div className="flex items-center gap-2">
        <input
          type="text"
          value={candidate}
          onChange={(e) => {
            setCandidate(e.target.value);
            void inspect(e.target.value);
          }}
          placeholder="C:\Program Files (x86)\Steam\steamapps\common\Halo Campaign Evolved"
          className="flex-1 min-w-0 px-3 py-2 rounded-lg text-sm bg-surface-primary border border-border-subtle
            text-text-primary placeholder-text-secondary/50 font-mono text-xs
            focus:outline-none focus:border-mjolnir-gold/50 focus:ring-1 focus:ring-mjolnir-gold/20
            transition-all duration-150"
        />
        <button
          onClick={handleBrowse}
          className="px-3 py-2 rounded-lg text-sm font-medium bg-surface-hover border border-border-subtle
            text-text-secondary hover:text-text-primary hover:border-mjolnir-gold/40
            transition-all duration-150 cursor-pointer whitespace-nowrap"
        >
          Browse…
        </button>
      </div>
      <p className="mt-1.5 text-xs text-text-secondary/70">
        The game folder, or anything inside it — <code className="text-[11px]">Meteorite</code>,
        the <code className="text-[11px]">Win64</code> folder, or the executable itself.
      </p>

      {check && (
        <p className={`mt-3 text-xs ${check.valid ? "text-accent-green" : "text-accent-red"}`}>
          {check.message}
        </p>
      )}

      {check?.valid && (
        <button
          onClick={() => void apply(check.resolved ?? candidate)}
          disabled={busy}
          className="mt-3 px-5 py-2.5 rounded-lg text-sm font-bold tracking-wide
            bg-gradient-to-r from-mjolnir-gold to-mjolnir-gold-dim text-surface-primary
            hover:brightness-110 active:brightness-90 disabled:opacity-50
            transition-all duration-150 cursor-pointer shadow-md shadow-mjolnir-gold/15"
        >
          {busy ? "Saving…" : "Use this folder"}
        </button>
      )}

      {error && <p className="mt-3 text-xs text-accent-red">{error}</p>}
    </section>
  );
}
