/**
 * Every update this launcher can perform, in one list.
 *
 * There are five sources — the launcher itself, the modpack/UE4SS core, hub
 * content mods, the signed code-mod set, and tools — and before this they
 * lived in five different corners of the UI, each with its own idea of what
 * "out of date" looked like. They are all the same question to a player, so
 * they get one shape here and one screen (`components/Updates.tsx`).
 *
 * Each item carries how to apply itself. That keeps the manager dumb: it
 * selects, orders and reports, and never learns what a modpack is.
 */
import { useCallback, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";

import type { UpdateState } from "../components/UpdaterBanner";
import type { UpdateInfo } from "../hub/library";

export type UpdateKind = "launcher" | "modpack" | "content" | "code" | "tool";

export interface UpdateItem {
  /** Stable across refreshes; the selection is keyed on it. */
  key: string;
  kind: UpdateKind;
  name: string;
  /** Null when the thing is installed but its version was never recorded. */
  from: string | null;
  to: string;
  /** Changelog or one-line summary, when the source has one. */
  detail: string | null;
  /**
   * Set when the only newer release is a pre-release. `newest_release` in
   * hub.rs prefers stable, so this means the mod has no stable release at
   * all — worth saying rather than quietly shipping someone a beta.
   */
  prerelease?: boolean;
  /** Restarts the launcher, so it is applied last and on its own. */
  restarts?: boolean;
  apply: () => Promise<void>;
}

export type ItemStatus = "idle" | "running" | "done" | "failed";

export interface UpdateProgress {
  status: ItemStatus;
  error?: string;
}

export interface UpdatesState {
  items: UpdateItem[];
  loading: boolean;
  /** Sources that could not be checked, e.g. offline. Not an error state. */
  warnings: string[];
  progress: Record<string, UpdateProgress>;
  applying: boolean;
  refresh: () => Promise<void>;
  apply: (keys: string[]) => Promise<void>;
}

interface CodeModRow {
  id: string;
  version: string;
  summary: string;
  installed_version: string | null;
  update_available: boolean;
}

interface CodeModsStatus {
  set_version: string;
  signature_verified: boolean;
  mods: CodeModRow[];
}

interface ToolStatus {
  id: string;
  name: string;
  installed_version: string | null;
  latest_version: string | null;
  update_available: boolean;
}

interface ModpackUpdate {
  installed_version: string | null;
  latest_version: string;
  latest_ue4ss_version: string;
  update_available: boolean;
  file_count: number;
}

export function useUpdates(updater: UpdateState): UpdatesState {
  const [items, setItems] = useState<UpdateItem[]>([]);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [progress, setProgress] = useState<Record<string, UpdateProgress>>({});
  const [applying, setApplying] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    const found: UpdateItem[] = [];
    const failed: string[] = [];

    // Sources are independent: one unreachable service must not hide the
    // updates the others found.
    const [modpack, content, code, tools] = await Promise.allSettled([
      invoke<ModpackUpdate>("check_modpack_update"),
      invoke<UpdateInfo[]>("hub_check_updates"),
      invoke<CodeModsStatus>("code_mods_status"),
      invoke<ToolStatus[]>("get_tools"),
    ]);

    if (modpack.status === "fulfilled") {
      const m = modpack.value;
      if (m.update_available) {
        found.push({
          key: "modpack",
          kind: "modpack",
          name: "MJOLNIR core",
          from: m.installed_version,
          to: m.latest_version,
          detail: `UE4SS ${m.latest_ue4ss_version} · ${m.file_count} files. This is the framework every other mod runs on.`,
          apply: () => invoke("install_modpack"),
        });
      }
    } else {
      failed.push("the release server (core install)");
    }

    if (content.status === "fulfilled") {
      for (const u of content.value) {
        found.push({
          key: `content:${u.slug}`,
          kind: "content",
          name: u.name,
          from: u.installed_version,
          to: u.latest_version,
          detail: u.changelog,
          prerelease: u.channel === "beta",
          apply: () =>
            invoke("hub_install", { slug: u.slug, releaseId: u.latest_release_id }),
        });
      }
    } else {
      failed.push("the hub (content mods)");
    }

    if (code.status === "fulfilled") {
      const status = code.value;
      for (const m of status.mods) {
        if (!m.update_available) continue;
        found.push({
          key: `code:${m.id}`,
          kind: "code",
          name: m.id,
          from: m.installed_version,
          to: m.version,
          detail: status.signature_verified
            ? m.summary || null
            : "The signed set does not verify — this will refuse to install.",
          apply: () => invoke("code_mods_install", { id: m.id }),
        });
      }
    } else {
      failed.push("the signed code-mod set");
    }

    if (tools.status === "fulfilled") {
      for (const t of tools.value) {
        if (!t.update_available || !t.latest_version) continue;
        found.push({
          key: `tool:${t.id}`,
          kind: "tool",
          name: t.name,
          from: t.installed_version,
          to: t.latest_version,
          detail: null,
          apply: () => invoke("install_tool", { id: t.id }),
        });
      }
    } else {
      failed.push("tool releases");
    }

    if (updater.status === "available" && updater.version) {
      found.push({
        key: "launcher",
        kind: "launcher",
        name: "MJOLNIR Launcher",
        from: null,
        to: updater.version,
        detail: "Installs and restarts the launcher.",
        restarts: true,
        apply: updater.handleInstall,
      });
    } else if (updater.checkError) {
      failed.push("launcher releases");
    }

    setItems(found);
    setWarnings(failed);
    setLoading(false);
  }, [updater.status, updater.version, updater.checkError, updater.handleInstall]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const apply = useCallback(
    async (keys: string[]) => {
      if (applying) return;
      setApplying(true);

      // Sequential on purpose: these write to the same game directory, and
      // the one that restarts the launcher has to be last.
      const queue = keys
        .map((k) => items.find((i) => i.key === k))
        .filter((i): i is UpdateItem => !!i)
        .sort((a, b) => Number(a.restarts ?? false) - Number(b.restarts ?? false));

      for (const item of queue) {
        setProgress((p) => ({ ...p, [item.key]: { status: "running" } }));
        try {
          await item.apply();
          setProgress((p) => ({ ...p, [item.key]: { status: "done" } }));
        } catch (e) {
          setProgress((p) => ({
            ...p,
            [item.key]: { status: "failed", error: String(e) },
          }));
        }
      }

      setApplying(false);
      await refresh();
    },
    [applying, items, refresh],
  );

  return { items, loading, warnings, progress, applying, refresh, apply };
}

export const KIND_LABEL: Record<UpdateKind, string> = {
  launcher: "Launcher",
  modpack: "Core",
  content: "Content mod",
  code: "Script mod",
  tool: "Tool",
};
