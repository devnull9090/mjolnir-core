import { useEditor, type Tab } from "../stores/editor-store";
import { snapshotTabUi, type TabUiState } from "./tab-ui";

/**
 * The open tabs as they persist across launches. A tab is stored by identity —
 * a tag's group and short path, an asset's virtual path — never by catalog
 * index, so a game update reshuffling the catalog invalidates nothing; a tab
 * whose identity no longer resolves is simply dropped on restore, the way a
 * stale recent is.
 */
export type PersistedTab = {
  kind: Tab["kind"];
  /** Tags only; null for assets addressed by path alone. */
  group: string | null;
  /** A tag's short path, or an asset's virtual filesystem path. */
  path: string;
  label: string;
  ui: TabUiState | null;
};

export type PersistedSession = { v: 1; tabs: PersistedTab[]; active: number };

const SESSION_KEY = "tag-editor-session";
/** Ceiling per map so one long-lived scenario tab cannot bloat the store. */
const UI_KEY_CAP = 500;
const SAVE_DEBOUNCE_MS = 400;

/**
 * Saving stays off until the launch restore has run (or decided there is
 * nothing to restore), so an early close cannot overwrite a good session with
 * an empty one.
 */
let restored = false;

export function markSessionRestored(): void {
  restored = true;
}

function capKeys<T>(record: Record<string, T>): Record<string, T> {
  const keys = Object.keys(record);
  if (keys.length <= UI_KEY_CAP) return record;
  const out: Record<string, T> = {};
  for (const k of keys.slice(keys.length - UI_KEY_CAP)) out[k] = record[k];
  return out;
}

function trimmedUi(ui: TabUiState | null): TabUiState | null {
  if (!ui) return null;
  return { scroll: ui.scroll, open: capKeys(ui.open), element: capKeys(ui.element) };
}

export function saveSession(): void {
  if (!restored) return;
  const s = useEditor.getState();
  if (s.status !== "ready") return;
  const tabs: PersistedTab[] = [];
  let active = -1;
  for (const t of s.tabs) {
    // A tab that never learned its identity (a mesh opened from an import
    // link, a tag whose peek has not landed) cannot be found again; it is
    // skipped now and picked up by the save after its identity arrives.
    if (!t.path || (t.kind === "tag" && !t.group)) continue;
    if (t.id === s.activeTab) active = tabs.length;
    tabs.push({
      kind: t.kind,
      group: t.group ?? null,
      path: t.path,
      label: t.label,
      ui: trimmedUi(snapshotTabUi(t.id)),
    });
  }
  try {
    localStorage.setItem(SESSION_KEY, JSON.stringify({ v: 1, tabs, active }));
  } catch {
    // Not persisting the session loses nothing but convenience.
  }
}

let saveTimer: number | undefined;

/** Debounced [saveSession], for scroll and toggle handlers. */
export function scheduleSaveSession(): void {
  window.clearTimeout(saveTimer);
  saveTimer = window.setTimeout(saveSession, SAVE_DEBOUNCE_MS);
}

// The last scroll or toggle before close may still be inside the debounce, so
// the close itself flushes.
window.addEventListener("beforeunload", saveSession);

function sanitizedUi(raw: unknown): TabUiState | null {
  if (typeof raw !== "object" || raw === null) return null;
  const r = raw as Record<string, unknown>;
  const ui: TabUiState = { scroll: {}, open: {}, element: {} };
  const scroll = r.scroll as Record<string, unknown> | undefined;
  for (const view of ["form", "tree"] as const) {
    const v = scroll?.[view];
    if (typeof v === "number" && Number.isFinite(v) && v >= 0) ui.scroll[view] = v;
  }
  if (typeof r.open === "object" && r.open !== null) {
    for (const [k, v] of Object.entries(r.open)) {
      if (typeof v === "boolean") ui.open[k] = v;
    }
  }
  if (typeof r.element === "object" && r.element !== null) {
    for (const [k, v] of Object.entries(r.element)) {
      if (typeof v === "number" && Number.isInteger(v) && v >= 0) ui.element[k] = v;
    }
  }
  return ui;
}

const KINDS: Tab["kind"][] = ["tag", "texture", "sound", "mesh"];

/** The stored session, validated row by row; garbage clears itself. */
export function loadStoredSession(): PersistedSession | null {
  let raw: string | null = null;
  try {
    raw = localStorage.getItem(SESSION_KEY);
  } catch {
    return null;
  }
  if (!raw) return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null) throw new Error("not an object");
    const p = parsed as Record<string, unknown>;
    if (p.v !== 1 || !Array.isArray(p.tabs)) throw new Error("wrong shape");
    const tabs: PersistedTab[] = [];
    for (const row of p.tabs as unknown[]) {
      if (typeof row !== "object" || row === null) continue;
      const t = row as Record<string, unknown>;
      if (!KINDS.includes(t.kind as Tab["kind"])) continue;
      if (typeof t.path !== "string" || t.path === "") continue;
      if (t.kind === "tag" && typeof t.group !== "string") continue;
      tabs.push({
        kind: t.kind as Tab["kind"],
        group: typeof t.group === "string" ? t.group : null,
        path: t.path,
        label: typeof t.label === "string" ? t.label : t.path,
        ui: sanitizedUi(t.ui),
      });
    }
    const active = typeof p.active === "number" ? p.active : -1;
    return { v: 1, tabs, active };
  } catch {
    try {
      localStorage.removeItem(SESSION_KEY);
    } catch {
      // It will fail validation again next launch; nothing else to do.
    }
    return null;
  }
}
