/**
 * What a launch checks first (src-tauri/src/preflight.rs, unsupported.rs):
 * the shapes the Rust side answers with, and how to fix each finding.
 *
 * Every Launch goes through this, and so does a join from a link that has to
 * start the game, and the update the game's own out-of-date prompt asks for
 * (`mjolnir://update`). docs/update_check.md describes the whole flow.
 */
import { createContext, useContext } from "react";
import { invoke } from "@tauri-apps/api/core";

export interface Outdated {
  kind: "core" | "code" | "content";
  id: string;
  name: string;
  installed: string | null;
  latest: string;
  release_id: string | null;
  repair: boolean;
}

export interface UnsupportedMod {
  kind: "pak" | "ue4ss";
  name: string;
  files: string[];
  bytes: number;
}

export interface UpdateCheck {
  checked_at: number;
  items: Outdated[];
  unreachable: string[];
  unsupported: UnsupportedMod[];
}

export interface Problem {
  kind: "core" | "code" | "content";
  id: string;
  name: string;
  detail: string;
  release_id: string | null;
}

export interface SetAsideResult {
  moved: number;
  failed: string[];
}

/** One step of an apply run: an update, a repair, or moving mods aside. */
export interface Step {
  key: string;
  label: string;
  run: () => Promise<void>;
}

/** Installs whatever `kind`/`id` names: the latest release, or for a hub mod
 *  the release given (the newest for an update, the installed one for a
 *  repair). The same commands the Updates screen applies with. */
function install(kind: Outdated["kind"], id: string, releaseId: string | null, task: string) {
  switch (kind) {
    case "core":
      return invoke<void>("install_modpack", { task });
    case "code":
      return invoke<void>("code_mods_install", { id, task });
    case "content":
      return invoke<void>("hub_install", { slug: id, releaseId, task }).then(() => undefined);
  }
}

export function updateStep(o: Outdated): Step {
  const key = `update:${o.kind}:${o.id}`;
  return {
    key,
    label: o.repair
      ? `Repair ${o.name} (v${o.latest})`
      : `Update ${o.name}${o.installed ? ` ${o.installed}` : ""} → ${o.latest}`,
    run: () => install(o.kind, o.id, o.release_id, key),
  };
}

export function repairStep(p: Problem): Step {
  const key = `repair:${p.kind}:${p.id}`;
  return {
    key,
    label: `Reinstall ${p.name}`,
    run: () => install(p.kind, p.id, p.release_id, key),
  };
}

export function setAsideStep(mods: UnsupportedMod[]): Step {
  return {
    key: "set-aside",
    label: `Move ${mods.length} unsupported mod${mods.length === 1 ? "" : "s"} aside`,
    run: async () => {
      const r = await invoke<SetAsideResult>("unsupported_set_aside");
      if (r.failed.length > 0) {
        throw new Error(
          `${r.failed.length} file${r.failed.length === 1 ? "" : "s"} could not be moved (is the game running?): ${r.failed[0]}`,
        );
      }
    },
  };
}

/**
 * Problems an update already fixes: reinstalling a mod that is about to be
 * updated would download it twice.
 */
export function repairsNotCovered(problems: Problem[], items: Outdated[]): Problem[] {
  return problems.filter((p) => !items.some((o) => o.kind === p.kind && o.id === p.id));
}

export interface PreflightRequest {
  /** Starts the game (or hands a join over); runs once the checks pass. */
  launch: () => Promise<void>;
  /**
   * The game asked for this (`mjolnir://update`): wait for it to close,
   * apply every update and repair without asking, and start it again.
   */
  update?: boolean;
}

export interface PreflightApi {
  /**
   * Run the checks, ask what to do when something is found, then launch.
   * Resolves `true` once `launch` ran, `false` when the player cancelled.
   * An error from `launch` itself rejects, for the caller to show.
   */
  run: (request: PreflightRequest) => Promise<boolean>;
}

export const PreflightContext = createContext<PreflightApi>({
  run: async (r) => {
    await r.launch();
    return true;
  },
});

export const usePreflight = () => useContext(PreflightContext);

export function formatSize(bytes: number): string {
  if (bytes >= 1 << 30) return `${(bytes / (1 << 30)).toFixed(1)} GB`;
  if (bytes >= 1 << 20) return `${(bytes / (1 << 20)).toFixed(0)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}
