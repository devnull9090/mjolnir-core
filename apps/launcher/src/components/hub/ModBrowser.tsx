/**
 * Browsing the community hub: search, filter, sort, page, install.
 *
 * The listing is the hub's `/mods` endpoint with every knob it offers, so
 * what the launcher can find matches what the website can find. Cards are
 * the shared <ModCard>; the launcher only supplies the action on the right.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ActionButton,
  Badge,
  ErrorNote,
  ModCard,
  SearchIcon,
  Spinner,
  useHub,
  type Mod,
  type ModSort,
  type ModType,
} from "@mjolnir/hub-kit";

import type { Library } from "../../hub/library";

const CATEGORIES = [
  "all",
  "gameplay",
  "maps",
  "textures",
  "weapons",
  "camera",
  "tools",
  "framework",
  "multiplayer",
];

const SORTS: { key: ModSort; label: string }[] = [
  { key: "newest", label: "Newest" },
  { key: "downloads", label: "Downloads" },
  { key: "rating", label: "Top rated" },
];

export function ModBrowser({
  library,
  onSelect,
}: {
  library: Library;
  onSelect: (slug: string) => void;
}) {
  const { client } = useHub();
  const [mods, setMods] = useState<Mod[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [category, setCategory] = useState("all");
  const [sort, setSort] = useState<ModSort>("newest");
  const [loading, setLoading] = useState(true);
  const [offline, setOffline] = useState<string | null>(null);

  // One request per pause in typing, not one per keystroke.
  useEffect(() => {
    const t = setTimeout(() => setDebounced(query.trim()), 250);
    return () => clearTimeout(t);
  }, [query]);

  const filters = useMemo(
    () => ({
      q: debounced || undefined,
      category: category === "all" ? undefined : category,
      // Content only: script and native mods install from the signed set on
      // the Code mods tab, so listing them here would offer an Install this
      // view cannot honour.
      type: "content" as ModType,
      sort,
      limit: 20,
    }),
    [debounced, category, sort],
  );

  // Guards against a slow first page landing after the filters moved on.
  const generation = useRef(0);

  const load = useCallback(
    async (append: boolean, after: string | null) => {
      const mine = ++generation.current;
      setLoading(true);
      try {
        const page = await client.listMods({ ...filters, cursor: after ?? undefined });
        if (mine !== generation.current) return;
        setMods((prev) => (append ? [...prev, ...page.mods] : page.mods));
        setCursor(page.next_cursor);
        setOffline(null);
      } catch (e) {
        if (mine !== generation.current) return;
        setOffline(e instanceof Error ? e.message : String(e));
      } finally {
        if (mine === generation.current) setLoading(false);
      }
    },
    [client, filters],
  );

  useEffect(() => {
    void load(false, null);
  }, [load]);

  const installedSlugs = new Set(library.state?.installed.map((m) => m.slug) ?? []);
  const updateFor = (slug: string) => library.updates.find((u) => u.slug === slug);
  const activeEntries = library.state?.profiles.find((p) => p.name === library.state?.active)
    ?.entries;

  const action = (mod: Mod) => {
    if (mod.type !== "content") {
      return (
        <Badge tone="blue" title="Code mods install from the signed set, on the Code mods tab.">
          Code mods tab
        </Badge>
      );
    }
    const installed = installedSlugs.has(mod.slug);
    const update = updateFor(mod.slug);
    const entry = activeEntries?.find((e) => e.slug === mod.slug);
    const busy = library.busy === mod.slug;

    if (!installed) {
      return (
        <ActionButton
          onClick={() => void library.run(mod.slug, "hub_install", { slug: mod.slug })}
          disabled={!!library.busy}
        >
          {busy ? <Spinner className="w-3.5 h-3.5" /> : null}
          {busy ? "Installing…" : "Install"}
        </ActionButton>
      );
    }
    return (
      <div className="flex items-center gap-2">
        {update && (
          <ActionButton
            onClick={() =>
              void library.run(mod.slug, "hub_install", {
                slug: mod.slug,
                releaseId: update.latest_release_id,
              })
            }
            disabled={!!library.busy}
            title={`Update to v${update.latest_version}`}
          >
            {busy ? "Updating…" : `Update → ${update.latest_version}`}
          </ActionButton>
        )}
        <ActionButton
          tone="neutral"
          onClick={() =>
            void library.run(mod.slug, "hub_set_enabled", {
              slug: mod.slug,
              enabled: !entry?.enabled,
            })
          }
          disabled={!!library.busy || !entry}
          title={
            entry
              ? "Enabled mods are written into the game's Paks directory"
              : "Installed, but not in this profile"
          }
        >
          {entry?.enabled ? "Enabled" : "Disabled"}
        </ActionButton>
      </div>
    );
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative flex-1 min-w-52">
          <SearchIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-secondary" />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search the hub…"
            className="w-full pl-9 pr-3 py-2 text-sm rounded-lg bg-surface-secondary border border-border-subtle focus:border-mjolnir-gold/60 focus:outline-none"
          />
        </div>
        <div className="flex items-center gap-1 text-xs">
          {SORTS.map((s) => (
            <button
              key={s.key}
              onClick={() => setSort(s.key)}
              className={`px-3 py-1.5 rounded-lg border transition-colors cursor-pointer ${
                sort === s.key
                  ? "border-mjolnir-gold/60 text-mjolnir-gold"
                  : "border-border-subtle text-text-secondary hover:text-text-primary"
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {CATEGORIES.map((c) => (
          <button
            key={c}
            onClick={() => setCategory(c)}
            className={`px-2.5 py-1 rounded-lg border text-xs capitalize transition-colors cursor-pointer ${
              category === c
                ? "border-mjolnir-gold/60 text-mjolnir-gold"
                : "border-border-subtle text-text-secondary hover:text-text-primary"
            }`}
          >
            {c}
          </button>
        ))}
      </div>

      {offline && (
        <ErrorNote>
          Could not reach the hub ({offline}). Installed mods keep working offline.
        </ErrorNote>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
        {mods.map((mod) => (
          <ModCard
            key={mod.id}
            mod={mod}
            onSelect={() => onSelect(mod.slug)}
            action={action(mod)}
            badges={
              installedSlugs.has(mod.slug) ? (
                <Badge tone="green" title="Installed on this machine">
                  installed
                </Badge>
              ) : null
            }
          />
        ))}
      </div>

      {loading && (
        <p className="flex items-center gap-2 text-sm text-text-secondary">
          <Spinner /> Loading…
        </p>
      )}
      {!loading && mods.length === 0 && !offline && (
        <p className="text-sm text-text-secondary">Nothing published matches that.</p>
      )}
      {cursor && !loading && (
        <ActionButton tone="neutral" onClick={() => void load(true, cursor)}>
          Load more
        </ActionButton>
      )}
    </div>
  );
}
