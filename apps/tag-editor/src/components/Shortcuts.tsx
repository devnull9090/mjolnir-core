import { useEffect } from "react";
import { useEditor } from "../stores/editor-store";

/** Move to the neighbouring tab, wrapping at the ends. */
function cycleTab(dir: 1 | -1) {
  const s = useEditor.getState();
  if (s.tabs.length < 2) return;
  const at = s.tabs.findIndex((t) => t.id === s.activeTab);
  const next = s.tabs[(at + dir + s.tabs.length) % s.tabs.length];
  if (next) void s.activateTab(next.id);
}

/**
 * The app's keyboard: one window-level listener, rendered as nothing.
 *
 * Alt+Left / Alt+Right — back / forward through visited documents.
 * Ctrl+P — quick-open palette (preventDefault, or the webview prints).
 * Ctrl+PageDown / Ctrl+PageUp — next / previous tab. Ctrl+Tab does the same
 * where the webview lets it through; PageDown is the pair that always works.
 * Ctrl+Z / Ctrl+Y (or Ctrl+Shift+Z) — undo / redo the active tag's edits,
 * unless the keys landed in a text field, whose own undo they belong to.
 *
 * None of the navigation combos collide with text editing, so a focused input
 * is no reason to swallow them. Escape stays local to whatever is open.
 */
function inTextField(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || target.isContentEditable;
}

export function Shortcuts() {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const s = useEditor.getState();
      if (e.altKey && !e.ctrlKey && e.key === "ArrowLeft") {
        e.preventDefault();
        s.goBack();
      } else if (e.altKey && !e.ctrlKey && e.key === "ArrowRight") {
        e.preventDefault();
        s.goForward();
      } else if (e.ctrlKey && !e.altKey && !e.shiftKey && e.key.toLowerCase() === "p") {
        e.preventDefault();
        s.setQuickOpen(!s.quickOpen);
      } else if (e.ctrlKey && (e.key === "PageDown" || e.key === "PageUp")) {
        e.preventDefault();
        cycleTab(e.key === "PageDown" ? 1 : -1);
      } else if (e.ctrlKey && e.key === "Tab") {
        e.preventDefault();
        cycleTab(e.shiftKey ? -1 : 1);
      } else if (e.ctrlKey && !e.altKey && e.key.toLowerCase() === "z" && !inTextField(e.target)) {
        const active = s.tabs.find((t) => t.id === s.activeTab);
        if (active?.kind !== "tag") return;
        e.preventDefault();
        if (e.shiftKey) void s.redoEdit();
        else void s.undoEdit();
      } else if (e.ctrlKey && !e.altKey && !e.shiftKey && e.key.toLowerCase() === "y" && !inTextField(e.target)) {
        const active = s.tabs.find((t) => t.id === s.activeTab);
        if (active?.kind !== "tag") return;
        e.preventDefault();
        void s.redoEdit();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  return null;
}
