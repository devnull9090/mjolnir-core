import type { Tab } from "../stores/editor-store";
import { useEditor } from "../stores/editor-store";

/** Short badge and colour for each document kind. */
const KINDS: Record<Tab["kind"], { badge: string; color: string }> = {
  tag: { badge: "tag", color: "text-mjolnir-gold" },
  texture: { badge: "tex", color: "text-accent-blue" },
  sound: { badge: "snd", color: "text-accent-green" },
  mesh: { badge: "msh", color: "text-accent-purple" },
};

/** The strip of open documents: tags, textures and sounds, with dirty markers. */
export function TabBar() {
  const { tabs, activeTab, dirtyTags } = useEditor();
  const activateTab = useEditor((s) => s.activateTab);
  const closeTab = useEditor((s) => s.closeTab);

  if (tabs.length === 0) return null;

  return (
    <div className="flex shrink-0 items-stretch overflow-x-auto border-b border-border-subtle bg-surface-secondary">
      {tabs.map((tab) => {
        const active = tab.id === activeTab;
        const dirty = tab.kind === "tag" && dirtyTags[tab.index];
        return (
          <div
            key={tab.id}
            className={`group flex max-w-56 shrink-0 items-center border-r border-border-subtle ${
              active
                ? "bg-surface-primary text-text-primary"
                : "text-text-dim hover:bg-surface-hover hover:text-text-secondary"
            }`}
          >
            <button
              type="button"
              onClick={() => void activateTab(tab.id)}
              onAuxClick={(e) => {
                if (e.button === 1) closeTab(tab.id);
              }}
              title={tab.label}
              className="flex min-w-0 items-center gap-1.5 py-1.5 pl-3 pr-1 text-xs"
            >
              <span className={`shrink-0 font-mono text-[9px] uppercase ${KINDS[tab.kind].color}`}>
                {KINDS[tab.kind].badge}
              </span>
              <span className="min-w-0 truncate font-mono">{tab.label}</span>
              {dirty && (
                <span className="shrink-0 text-mjolnir-gold" title="Unexported edits">
                  ●
                </span>
              )}
            </button>
            <button
              type="button"
              onClick={() => closeTab(tab.id)}
              title={dirty ? "Close (edits are kept until exported or reverted)" : "Close"}
              className="shrink-0 px-1.5 py-1.5 text-[11px] text-text-dim opacity-0 hover:text-text-primary group-hover:opacity-100"
            >
              ×
            </button>
          </div>
        );
      })}
    </div>
  );
}
