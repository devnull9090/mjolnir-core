/**
 * The launcher's own view of the hub: what is installed, what is out of
 * date, what still hashes to what it should, and what conflicts with what.
 *
 * All of it comes from Rust commands rather than the API, because all of it
 * is about this machine. The catalogue side (browsing, ratings, comments)
 * goes through the shared HubClient instead.
 */
import { useCallback, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";

export interface InstalledMod {
  slug: string;
  name: string;
  release_id: string;
  version: string;
  sha256: string;
  containers: string[];
  summary: string | null;
  author: string | null;
  category: string | null;
  installed_at: number | null;
  signature_verified: boolean;
  container_hashes: Record<string, string>;
  /** Author signing-key fingerprint this launcher verified at install. */
  signer_fingerprint?: string | null;
  /** Hub account id that published the installed release. */
  published_by?: string | null;
  /** Key changed / signature disappeared / key revoked — worth keeping
   *  in front of the user. */
  signature_notice?: string | null;
}

export interface ProfileEntry {
  slug: string;
  enabled: boolean;
}

export interface Profile {
  name: string;
  entries: ProfileEntry[];
}

export interface HubState {
  installed: InstalledMod[];
  profiles: Profile[];
  active: string;
}

export interface UpdateInfo {
  slug: string;
  name: string;
  installed_version: string;
  latest_version: string;
  latest_release_id: string;
  channel: string;
  changelog: string | null;
}

export interface VerifiedMod {
  slug: string;
  ok: boolean;
  tampered: string[];
  missing: string[];
  signature_verified: boolean;
}

export interface ConflictPair {
  a: string;
  b: string;
  shared_chunks: number;
}

export interface Library {
  state: HubState | null;
  updates: UpdateInfo[];
  verified: Record<string, VerifiedMod>;
  conflicts: ConflictPair[];
  /** Key of whatever action is in flight, for per-row spinners. */
  busy: string | null;
  error: string | null;
  clearError: () => void;
  refresh: () => Promise<void>;
  checkUpdates: () => Promise<void>;
  /** Runs a state-changing command and folds the new state back in. */
  run: (key: string, command: string, args?: Record<string, unknown>) => Promise<boolean>;
}

export function useHubLibrary(): Library {
  const [state, setState] = useState<HubState | null>(null);
  const [updates, setUpdates] = useState<UpdateInfo[]>([]);
  const [verified, setVerified] = useState<Record<string, VerifiedMod>>({});
  const [conflicts, setConflicts] = useState<ConflictPair[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setState(await invoke<HubState>("hub_state"));
      // A read that succeeds clears whatever the last one complained about;
      // a stale error next to correct data is its own kind of confusing.
      setError(null);
    } catch (e) {
      // Without this the view would render an empty library next to a
      // banner announcing updates for mods it claims not to have.
      setError(`Cannot read the installed mods: ${e}`);
      return;
    }

    // Integrity is local and always available; conflicts need the hub, so a
    // machine that is offline keeps the rest of the view working.
    void invoke<VerifiedMod[]>("hub_verify_installed")
      .then((rows) => setVerified(Object.fromEntries(rows.map((r) => [r.slug, r]))))
      .catch(() => setVerified({}));
    void invoke<{ pairs: ConflictPair[] }>("hub_check_conflicts")
      .then((r) => setConflicts(r.pairs))
      .catch(() => setConflicts([]));
  }, []);

  const checkUpdates = useCallback(async () => {
    try {
      setUpdates(await invoke<UpdateInfo[]>("hub_check_updates"));
    } catch {
      setUpdates([]);
    }
  }, []);

  useEffect(() => {
    void refresh().then(checkUpdates);
  }, [refresh, checkUpdates]);

  const run = useCallback(
    async (key: string, command: string, args?: Record<string, unknown>) => {
      setBusy(key);
      setError(null);
      try {
        const next = await invoke<HubState>(command, args);
        // Every mutating hub command answers with the new state.
        if (next && typeof next === "object" && "installed" in next) setState(next);
        await refresh();
        await checkUpdates();
        return true;
      } catch (e) {
        setError(String(e));
        return false;
      } finally {
        setBusy(null);
      }
    },
    [refresh, checkUpdates],
  );

  return {
    state,
    updates,
    verified,
    conflicts,
    busy,
    error,
    clearError: () => setError(null),
    refresh,
    checkUpdates,
    run,
  };
}

/** Conflicts touching one mod, resolved from release ids to slugs. */
export function conflictsFor(
  slug: string,
  state: HubState | null,
  conflicts: ConflictPair[],
): { other: string; chunks: number }[] {
  if (!state) return [];
  const toSlug = new Map(state.installed.map((m) => [m.release_id, m.slug]));
  return conflicts
    .filter((p) => toSlug.get(p.a) === slug || toSlug.get(p.b) === slug)
    .map((p) => ({
      other: (toSlug.get(p.a) === slug ? toSlug.get(p.b) : toSlug.get(p.a)) ?? "another mod",
      chunks: p.shared_chunks,
    }));
}
