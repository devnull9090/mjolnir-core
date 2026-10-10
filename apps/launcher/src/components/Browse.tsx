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

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold">Browse the Hub</h2>
          <p className="text-sm text-text-secondary mt-0.5">
            Everything published on mjolnircore.com. Installed mods are managed under My Mods.
          </p>
        </div>
      </div>

      <div className="flex items-center gap-1">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => onTab(t.key)}
            title={t.hint}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors cursor-pointer ${
              tab === t.key
                ? "bg-surface-card text-text-primary"
                : "text-text-secondary hover:text-text-primary"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "content" && <ModBrowser library={library} onSelect={onOpenMod} />}
      {tab === "maps" && <MapBrowser library={library} onSelect={onOpenMod} />}
      {tab === "code" && <CodeModsPanel />}
    </div>
  );
}
