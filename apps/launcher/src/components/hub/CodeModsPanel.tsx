/**
 * The signed code-mod set.
 *
 * Script mods can execute, so they never travel through open upload: they
 * are reviewed in mjolnir-core, built in CI, and covered by an Ed25519
 * signature this launcher verifies against a key compiled into the binary.
 * If that signature does not verify, nothing here installs — the badge at
 * the top is the whole trust story, so it is the first thing on the panel.
 */
import { useCallback, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import {
  ActionButton,
  Badge,
  ErrorNote,
  ShieldIcon,
  Spinner,
  formatBytes,
  shortHash,
} from "@mjolnir/hub-kit";

interface CodeModRow {
  id: string;
  file: string;
  sha256: string;
  size: number;
  version: string;
  summary: string;
  category: string;
  installed_version: string | null;
  update_available: boolean;
  integrity: "not_installed" | "verified" | "modified" | "unverified";
}

interface CodeModsStatus {
  set_version: string;
  signature_verified: boolean;
  mods: CodeModRow[];
}

export function CodeModsPanel() {
  const [status, setStatus] = useState<CodeModsStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    invoke<CodeModsStatus>("code_mods_status")
      .then(setStatus)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, []);

  useEffect(load, [load]);

  const install = async (id: string) => {
    setBusy(id);
    setError(null);
    try {
      await invoke("code_mods_install", { id });
      load();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-xl font-bold flex items-center gap-2">
          Code mods
          {status &&
            (status.signature_verified ? (
              <Badge tone="green" title="manifest.json.sig verified against the pinned key">
                <ShieldIcon className="w-3 h-3" />
                signature verified · set v{status.set_version}
              </Badge>
            ) : (
              <Badge tone="red">signature failed — installs disabled</Badge>
            ))}
        </h2>
        <p className="text-sm text-text-secondary mt-0.5">
          UE4SS script mods, reviewed in mjolnir-core and shipped as an Ed25519-signed set. This
          launcher verifies the signature before installing anything.
        </p>
      </div>

      {error && <ErrorNote>{error}</ErrorNote>}

      {loading && !status ? (
        <p className="flex items-center gap-2 text-sm text-text-secondary">
          <Spinner /> Fetching the signed manifest…
        </p>
      ) : !status ? (
        <p className="text-sm text-text-secondary">No signed set published yet.</p>
      ) : (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
          {status.mods.map((m) => {
            const installed = m.installed_version !== null;
            // "Installed" is only a resting state when the bytes still check
            // out; anything else offers the fix, which is always a reinstall.
            const repairable = installed && m.integrity !== "verified";
            return (
              <div
                key={m.id}
                className="bg-surface-secondary border border-border-subtle rounded-xl px-4 py-3 flex items-center gap-3"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-semibold">{m.id}</span>
                    <Badge>v{m.version}</Badge>
                    {m.category && <Badge>{m.category}</Badge>}
                    {m.update_available && <Badge tone="gold">update</Badge>}
                    {m.integrity === "verified" && (
                      <Badge tone="blue" title="The installed files still hash to what the launcher extracted.">
                        <ShieldIcon className="w-3 h-3" />
                        verified
                      </Badge>
                    )}
                    {m.integrity === "modified" && (
                      <Badge tone="red" title="The installed files have changed since the launcher extracted them.">
                        modified
                      </Badge>
                    )}
                    {m.integrity === "unverified" && (
                      <Badge tone="amber" title="Present on disk, but not installed by this launcher — nothing to check it against.">
                        unverified
                      </Badge>
                    )}
                  </div>
                  {m.summary && (
                    <p className="text-xs text-text-secondary mt-0.5 line-clamp-1">{m.summary}</p>
                  )}
                  <p className="text-xs text-text-secondary font-mono truncate" title={m.sha256}>
                    {formatBytes(m.size)} · sha256 {shortHash(m.sha256)}
                  </p>
                </div>
                <ActionButton
                  size="sm"
                  disabled={
                    !!busy ||
                    (installed && !m.update_available && !repairable) ||
                    !status.signature_verified
                  }
                  title={
                    status.signature_verified
                      ? undefined
                      : "The set's signature does not verify; nothing from it will install."
                  }
                  onClick={() => void install(m.id)}
                >
                  {busy === m.id
                    ? "Installing…"
                    : m.update_available
                      ? "Update"
                      : repairable
                        ? "Reinstall"
                        : installed
                          ? "Installed"
                          : "Install"}
                </ActionButton>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
