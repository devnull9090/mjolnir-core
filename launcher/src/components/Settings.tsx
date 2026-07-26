import { useState, useEffect, useCallback } from "react";
import { invoke } from "@tauri-apps/api/core";
import { open } from "@tauri-apps/plugin-dialog";

interface LauncherSettings {
  launch_method: string;
  custom_exe_path: string | null;
}

interface BuildInfo {
  launcher_version: string;
  game_found: boolean;
  install_path: string | null;
  ue4ss_installed: boolean;
  mods_path: string | null;
  mods_count: number;
}

interface VerifyResult {
  checked: number;
  passed: number;
  failed: string[];
  missing: string[];
}

export default function Settings() {
  const [settings, setSettings] = useState<LauncherSettings>({
    launch_method: "steam",
    custom_exe_path: null,
  });
  const [buildInfo, setBuildInfo] = useState<BuildInfo | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Verify state
  const [verifying, setVerifying] = useState(false);
  const [verifyResult, setVerifyResult] = useState<VerifyResult | null>(null);
  const [verifyError, setVerifyError] = useState<string | null>(null);

  // Uninstall state
  const [confirmUninstall, setConfirmUninstall] = useState(false);
  const [uninstalling, setUninstalling] = useState(false);

  const loadData = useCallback(async () => {
    try {
      const [s, b] = await Promise.all([
        invoke<LauncherSettings>("get_settings"),
        invoke<BuildInfo>("get_build_info"),
      ]);
      setSettings(s);
      setBuildInfo(b);
    } catch (err) {
      console.error("Failed to load settings:", err);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleSave = async () => {
    setSaving(true);
    setSaved(false);
    setError(null);
    try {
      await invoke("save_settings", { settings });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch (err) {
      setError(String(err));
    } finally {
      setSaving(false);
    }
  };

  const handleBrowse = async () => {
    try {
      const selected = await open({
        multiple: false,
        filters: [{ name: "Executable", extensions: ["exe"] }],
      });
      if (selected) {
        setSettings((prev) => ({
          ...prev,
          custom_exe_path: selected as string,
        }));
      }
    } catch (err) {
      console.error("File dialog error:", err);
    }
  };

  const handleVerify = async () => {
    setVerifying(true);
    setVerifyResult(null);
    setVerifyError(null);
    try {
      const result = await invoke<VerifyResult>("verify_install");
      setVerifyResult(result);
    } catch (err) {
      setVerifyError(String(err));
    } finally {
      setVerifying(false);
    }
  };

  const handleUninstall = async () => {
    setUninstalling(true);
    try {
      await invoke("uninstall_modpack");
      setConfirmUninstall(false);
      // Reload to reflect changes
      loadData();
    } catch (err) {
      setError(String(err));
    } finally {
      setUninstalling(false);
    }
  };

  return (
    <div className="max-w-2xl">
      <h2 className="text-xl font-bold text-text-primary mb-1">Settings</h2>
      <p className="text-sm text-text-secondary mb-8">
        Configure how MJOLNIR launches your game and view system info.
      </p>

      {/* ── Launch Configuration ── */}
      <section className="mb-8">
        <h3 className="text-sm font-semibold text-text-primary uppercase tracking-wider mb-4 flex items-center gap-2">
          <svg className="w-4 h-4 text-mjolnir-gold" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          Launch Configuration
        </h3>

        <div className="space-y-3">
          {/* Steam option */}
          <label
            className={`flex items-start gap-3 p-4 rounded-xl border cursor-pointer transition-all duration-200
              ${settings.launch_method === "steam"
                ? "bg-surface-card border-mjolnir-gold/40 shadow-sm shadow-mjolnir-gold/5"
                : "bg-surface-primary border-border-subtle hover:border-border-subtle/80"
              }`}
          >
            <input
              type="radio"
              name="launch_method"
              value="steam"
              checked={settings.launch_method === "steam"}
              onChange={() => setSettings((prev) => ({ ...prev, launch_method: "steam" }))}
              className="mt-0.5 accent-mjolnir-gold"
            />
            <div>
              <span className="text-sm font-medium text-text-primary">Launch via Steam</span>
              <p className="text-xs text-text-secondary mt-0.5">
                Opens <code className="text-[11px] bg-surface-hover px-1 py-0.5 rounded">steam://rungameid/2806050</code> — recommended for Steam users
              </p>
            </div>
          </label>

          {/* Game Pass option */}
          <label
            className={`flex items-start gap-3 p-4 rounded-xl border cursor-pointer transition-all duration-200
              ${settings.launch_method === "gamepass"
                ? "bg-surface-card border-mjolnir-gold/40 shadow-sm shadow-mjolnir-gold/5"
                : "bg-surface-primary border-border-subtle hover:border-border-subtle/80"
              }`}
          >
            <input
              type="radio"
              name="launch_method"
              value="gamepass"
              checked={settings.launch_method === "gamepass"}
              onChange={() => setSettings((prev) => ({ ...prev, launch_method: "gamepass" }))}
              className="mt-0.5 accent-mjolnir-gold"
            />
            <div>
              <span className="text-sm font-medium text-text-primary">Launch via Game Pass</span>
              <p className="text-xs text-text-secondary mt-0.5">
                Launches via Xbox app — for PC Game Pass / Microsoft Store users
              </p>
            </div>
          </label>

          {/* Direct EXE option */}
          <label
            className={`flex items-start gap-3 p-4 rounded-xl border cursor-pointer transition-all duration-200
              ${settings.launch_method === "exe"
                ? "bg-surface-card border-mjolnir-gold/40 shadow-sm shadow-mjolnir-gold/5"
                : "bg-surface-primary border-border-subtle hover:border-border-subtle/80"
              }`}
          >
            <input
              type="radio"
              name="launch_method"
              value="exe"
              checked={settings.launch_method === "exe"}
              onChange={() => setSettings((prev) => ({ ...prev, launch_method: "exe" }))}
              className="mt-0.5 accent-mjolnir-gold"
            />
            <div className="flex-1">
              <span className="text-sm font-medium text-text-primary">Launch EXE directly</span>
              <p className="text-xs text-text-secondary mt-0.5">
                Run a specific game executable — useful for non-Steam installs or custom builds
              </p>
            </div>
          </label>

          {/* EXE path input */}
          {settings.launch_method === "exe" && (
            <div className="ml-7 mt-1 flex items-center gap-2">
              <input
                type="text"
                value={settings.custom_exe_path ?? ""}
                onChange={(e) =>
                  setSettings((prev) => ({
                    ...prev,
                    custom_exe_path: e.target.value || null,
                  }))
                }
                placeholder="C:\...\Meteorite-Win64-Shipping.exe"
                className="flex-1 px-3 py-2 rounded-lg text-sm bg-surface-primary border border-border-subtle
                  text-text-primary placeholder-text-secondary/50
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
          )}
        </div>

        {/* Save button */}
        <div className="mt-5 flex items-center gap-3">
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-5 py-2.5 rounded-lg text-sm font-bold tracking-wide
              bg-gradient-to-r from-mjolnir-gold to-mjolnir-gold-dim text-surface-primary
              hover:brightness-110 active:brightness-90 disabled:opacity-50
              transition-all duration-150 cursor-pointer
              shadow-md shadow-mjolnir-gold/15"
          >
            {saving ? "Saving…" : "Save Settings"}
          </button>
          {saved && (
            <span className="text-xs text-accent-green font-medium animate-pulse">
              ✓ Settings saved
            </span>
          )}
          {error && (
            <span className="text-xs text-accent-red font-medium">{error}</span>
          )}
        </div>
      </section>

      <hr className="border-border-subtle mb-8" />

      {/* ── Installation Management ── */}
      <section className="mb-8">
        <h3 className="text-sm font-semibold text-text-primary uppercase tracking-wider mb-4 flex items-center gap-2">
          <svg className="w-4 h-4 text-mjolnir-gold" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
          </svg>
          Installation Management
        </h3>

        <div className="flex items-center gap-3 mb-4">
          {/* Verify button */}
          <button
            onClick={handleVerify}
            disabled={verifying}
            className="px-4 py-2 rounded-lg text-sm font-medium bg-surface-card border border-border-subtle
              text-text-secondary hover:text-text-primary hover:border-accent-blue/40
              disabled:opacity-50 transition-all duration-150 cursor-pointer"
          >
            {verifying ? (
              <span className="flex items-center gap-2">
                <span className="w-3 h-3 border-2 border-accent-blue border-t-transparent rounded-full animate-spin" />
                Verifying…
              </span>
            ) : (
              "🔍 Verify Installation"
            )}
          </button>

          {/* Uninstall button */}
          {!confirmUninstall ? (
            <button
              onClick={() => setConfirmUninstall(true)}
              className="px-4 py-2 rounded-lg text-sm font-medium bg-surface-card border border-border-subtle
                text-text-secondary hover:text-accent-red hover:border-accent-red/40
                transition-all duration-150 cursor-pointer"
            >
              🗑 Uninstall Mods
            </button>
          ) : (
            <div className="flex items-center gap-2">
              <span className="text-xs text-accent-red font-medium">Are you sure?</span>
              <button
                onClick={handleUninstall}
                disabled={uninstalling}
                className="px-3 py-1.5 rounded-lg text-xs font-bold bg-accent-red text-white
                  hover:brightness-110 disabled:opacity-50 transition-all duration-150 cursor-pointer"
              >
                {uninstalling ? "Removing…" : "Yes, Uninstall"}
              </button>
              <button
                onClick={() => setConfirmUninstall(false)}
                className="px-3 py-1.5 rounded-lg text-xs font-medium bg-surface-hover text-text-secondary
                  hover:text-text-primary transition-all duration-150 cursor-pointer"
              >
                Cancel
              </button>
            </div>
          )}
        </div>

        {/* Verify results */}
        {verifyResult && (
          <div
            className={`rounded-xl border p-4 text-sm ${
              verifyResult.failed.length === 0 && verifyResult.missing.length === 0
                ? "bg-accent-green/8 border-accent-green/30"
                : "bg-accent-red/8 border-accent-red/30"
            }`}
          >
            <div className="flex items-center gap-2 mb-2">
              {verifyResult.failed.length === 0 && verifyResult.missing.length === 0 ? (
                <>
                  <svg className="w-5 h-5 text-accent-green" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                  <span className="font-semibold text-accent-green">
                    All {verifyResult.passed} files verified
                  </span>
                </>
              ) : (
                <>
                  <svg className="w-5 h-5 text-accent-red" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4.5c-.77-.833-2.694-.833-3.464 0L3.34 16.5c-.77.833.192 2.5 1.732 2.5z" />
                  </svg>
                  <span className="font-semibold text-accent-red">
                    {verifyResult.failed.length + verifyResult.missing.length} issue(s) found
                  </span>
                </>
              )}
            </div>

            <p className="text-xs text-text-secondary mb-1">
              Checked: {verifyResult.checked} · Passed: {verifyResult.passed}
            </p>

            {verifyResult.missing.length > 0 && (
              <div className="mt-2">
                <p className="text-xs font-medium text-accent-red mb-1">Missing files:</p>
                <ul className="text-xs text-text-secondary space-y-0.5 font-mono">
                  {verifyResult.missing.map((f) => (
                    <li key={f}>• {f}</li>
                  ))}
                </ul>
              </div>
            )}

            {verifyResult.failed.length > 0 && (
              <div className="mt-2">
                <p className="text-xs font-medium text-accent-red mb-1">Checksum mismatch:</p>
                <ul className="text-xs text-text-secondary space-y-0.5 font-mono">
                  {verifyResult.failed.map((f) => (
                    <li key={f}>• {f}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {verifyError && (
          <div className="rounded-xl border border-accent-red/30 bg-accent-red/8 p-3 text-sm">
            <p className="text-accent-red font-medium text-xs">{verifyError}</p>
          </div>
        )}
      </section>

      <hr className="border-border-subtle mb-8" />

      {/* ── Build & System Info ── */}
      <section>
        <h3 className="text-sm font-semibold text-text-primary uppercase tracking-wider mb-4 flex items-center gap-2">
          <svg className="w-4 h-4 text-mjolnir-gold" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          Build &amp; System Info
        </h3>

        {buildInfo ? (
          <div className="rounded-xl border border-border-subtle bg-surface-card overflow-hidden">
            <InfoRow label="Launcher Version" value={`v${buildInfo.launcher_version}`} highlight />
            <InfoRow
              label="Game Detected"
              value={buildInfo.game_found ? "Yes" : "No"}
              valueClass={buildInfo.game_found ? "text-accent-green" : "text-accent-red"}
            />
            <InfoRow label="Install Path" value={buildInfo.install_path ?? "—"} mono />
            <InfoRow
              label="UE4SS Status"
              value={buildInfo.ue4ss_installed ? "Installed" : "Not Installed"}
              valueClass={buildInfo.ue4ss_installed ? "text-accent-green" : "text-text-secondary"}
            />
            <InfoRow label="Mods Directory" value={buildInfo.mods_path ?? "—"} mono />
            <InfoRow label="Mods Loaded" value={String(buildInfo.mods_count)} last />
          </div>
        ) : (
          <div className="flex items-center justify-center h-24">
            <div className="w-5 h-5 border-2 border-mjolnir-gold border-t-transparent rounded-full animate-spin" />
          </div>
        )}
      </section>
    </div>
  );
}

function InfoRow({
  label,
  value,
  mono,
  highlight,
  valueClass,
  last,
}: {
  label: string;
  value: string;
  mono?: boolean;
  highlight?: boolean;
  valueClass?: string;
  last?: boolean;
}) {
  return (
    <div
      className={`flex items-center justify-between px-4 py-3 text-sm ${
        last ? "" : "border-b border-border-subtle/50"
      }`}
    >
      <span className="text-text-secondary">{label}</span>
      <span
        className={`${
          highlight
            ? "text-mjolnir-gold font-semibold"
            : valueClass ?? "text-text-primary"
        } ${mono ? "font-mono text-xs" : ""}`}
      >
        {value}
      </span>
    </div>
  );
}
