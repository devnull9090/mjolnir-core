import { useEditor } from "../stores/editor-store";

/**
 * UI state a tab keeps across switches: where it was scrolled, which sections
 * were open, which element each block's dropdown showed.
 *
 * Lives in a module map rather than the store: the inspector remounts on every
 * activation, so components read it once on mount and write through on change,
 * and nothing needs to re-render when it moves.
 */
export type TabUiState = {
  /** scrollTop of the inspector container, per view that scrolls. */
  scroll: Partial<Record<"form" | "tree", number>>;
  /** Expand/collapse choices by field path; an absent path means the default. */
  open: Record<string, boolean>;
  /** Selected element index per block or array path. */
  element: Record<string, number>;
};

const uiByTab = new Map<number, TabUiState>();

/** The tab's UI state, created empty on first ask. */
export function tabUi(tabId: number): TabUiState {
  let state = uiByTab.get(tabId);
  if (!state) {
    state = { scroll: {}, open: {}, element: {} };
    uiByTab.set(tabId, state);
  }
  return state;
}

/** Install restored state for a tab, replacing whatever it had. */
export function seedTabUi(tabId: number, state: TabUiState): void {
  uiByTab.set(tabId, state);
}

/** The tab's UI state as it stands, or null if it never accrued any. */
export function snapshotTabUi(tabId: number): TabUiState | null {
  return uiByTab.get(tabId) ?? null;
}

/** Forget a closed tab's UI state. */
export function dropTabUi(tabId: number): void {
  uiByTab.delete(tabId);
}

/**
 * The active tab's UI state. The inspectors are keyed by tab id, so within one
 * mounted inspector this is one stable object to read at init and mutate on
 * change.
 */
export function useTabUi(): TabUiState | null {
  const tabId = useEditor((s) => s.activeTab);
  return tabId === null ? null : tabUi(tabId);
}
