/**
 * Browse Hub — finding things, not managing them.
 *
 * This view used to also own the installed list and the load order, which
 * put "your mods" in two places at once. Installed things now live under My
 * Mods; what is left here is discovery: the community catalogue and the
 * signed code-mod set, each with an Install button and a full mod page.
 *
 * Everything the catalogue renders — cards, galleries, ratings, reviews,
 * comments, release lists — is the same component the website renders
 * (hub/src/kit). This file is the launcher's shell around it.
 */
import type { Library } from "../hub/library";
import { ModBrowser } from "./hub/ModBrowser";
import { MapBrowser } from "./hub/MapBrowser";
import { CodeModsPanel } from "./hub/CodeModsPanel";

export type BrowseTab = "content" | "maps" | "code";

/**
 * The tab is the caller's, not this view's: a `mjolnir://map/...` link opens
 * the Maps tab, and Back from a map's page has to land there again.
 */
export default function Browse({
  library,
  onOpenMod,
  tab,
  onTab,
}: {
  library: Library;
  onOpenMod: (slug: string) => void;
  tab: BrowseTab;
  onTab: (tab: BrowseTab) => void;
}) {
  const tabs: { key: BrowseTab; label: string; hint: string }[] = [
    { key: "content", label: "Content mods", hint: "Community game data — textures, weapons, tuning" },
    { key: "maps", label: "Maps", hint: "The classic maps and community maps, by game type and size" },
    { key: "code", label: "Code mods", hint: "Signed UE4SS scripts from mjolnir-core" },
  ];

  const activeTab = tabs.find((t) => t.key === tab) ?? tabs[0];

  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold">Browse the Hub</h2>
          <p className="text-sm text-text-secondary mt-0.5">
            {activeTab.hint}. Installed mods are managed under My Mods.
          </p>
        </div>

        <div
          role="tablist"
          aria-label="Browse category"
          className="inline-flex items-center gap-1 rounded-xl border border-border-subtle bg-surface-secondary p-1"
        >
          {tabs.map((t) => {
            const active = tab === t.key;
            return (
              <button
                key={t.key}
                type="button"
                role="tab"
                aria-selected={active}
                onClick={() => onTab(t.key)}
                title={t.hint}
                className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all duration-150 cursor-pointer ${
                  active
                    ? "bg-mjolnir-gold/16 text-mjolnir-gold shadow-[inset_0_0_0_1px_rgba(212,168,67,0.3)]"
                    : "text-text-secondary hover:text-text-primary hover:bg-surface-hover/50"
                }`}
              >
                {t.label}
              </button>
            );
          })}
        </div>
      </div>

      <div key={tab} className="launcher-view">
        {tab === "content" && <ModBrowser library={library} onSelect={onOpenMod} />}
        {tab === "maps" && <MapBrowser library={library} onSelect={onOpenMod} />}
        {tab === "code" && <CodeModsPanel />}
      </div>
    </div>
  );
}
