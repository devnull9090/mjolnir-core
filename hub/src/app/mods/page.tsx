import type { Metadata } from "next";
import { Package, Plus, Search } from "lucide-react";
import { getCloudflareContext } from "@opennextjs/cloudflare";

import { ModCard } from "../components/HubKit";
import { ButtonLink, EmptyState, FilterBar, FilterChips, PageHeader, PageShell, SelectNav } from "../components/ui";
import { listPublishedMods } from "@/lib/api/queries";

export const metadata: Metadata = {
  title: "Mods | MJOLNIR Core",
  description: "Browse and download community mods for Halo Campaign Evolved.",
};

const CATEGORIES = ["all", "gameplay", "maps", "forge", "textures", "weapons", "camera", "tools", "framework", "multiplayer"];
const SORTS = [
  { key: "newest", label: "Newest" },
  { key: "downloads", label: "Most downloaded" },
  { key: "rating", label: "Top rated" },
] as const;

export default async function ModsPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; category?: string; sort?: string }>;
}) {
  const params = await searchParams;
  const q = params.q?.trim() || undefined;
  const category = params.category || "all";
  const sort = (["newest", "downloads", "rating"] as const).find((s) => s === params.sort) ?? "newest";

  const { env } = getCloudflareContext();
  // Maps have their own catalog with its own filters, at /maps.
  const mods = await listPublishedMods(env.DB as never, { q, category, sort, map: false });

  const qs = (over: Record<string, string>) => {
    const merged = { q: q ?? "", category, sort, ...over };
    const u = new URLSearchParams();
    for (const [k, v] of Object.entries(merged)) if (v && v !== "all" && v !== "newest") u.set(k, v);
    const s = u.toString();
    return s ? `/mods?${s}` : "/mods";
  };

  return (
    <PageShell>
      <PageHeader
        eyebrow="Community workshop"
        title="Mods"
        description="Gameplay tweaks, textures, weapons, cameras and the framework itself, for Halo Campaign Evolved. Every download is scanned; anything that runs code is signed."
        actions={
          <ButtonLink href="/mods/new">
            <Plus aria-hidden className="h-4 w-4" />
            Publish a mod
          </ButtonLink>
        }
      />

      <FilterBar>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <form action="/mods" method="get" role="search" className="relative sm:w-72">
            <label htmlFor="mod-search" className="sr-only">
              Search mods
            </label>
            <Search
              aria-hidden
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted"
            />
            <input
              id="mod-search"
              type="search"
              name="q"
              defaultValue={q ?? ""}
              placeholder="Search mods…"
              className="min-h-10 w-full rounded-lg border border-border bg-surface-raised pl-9 pr-3 text-sm text-foreground placeholder:text-text-muted hover:border-border-bright focus:border-gold/60"
            />
            {category !== "all" && <input type="hidden" name="category" value={category} />}
            {sort !== "newest" && <input type="hidden" name="sort" value={sort} />}
          </form>
          <SelectNav
            label="Sort"
            name="sort"
            value={sort}
            action="/mods"
            hidden={{ q, category: category === "all" ? undefined : category }}
            options={SORTS.map((s) => ({ value: s.key, label: s.label, href: qs({ sort: s.key }) }))}
          />
        </div>
        <FilterChips
          label="Category"
          options={CATEGORIES.map((cat) => ({
            label: cat === "all" ? "All mods" : cat === "forge" ? "Forge packs" : cat[0].toUpperCase() + cat.slice(1),
            // Maps have their own catalog.
            href: cat === "maps" ? "/maps" : cat === "forge" ? "/forge" : qs({ category: cat }),
            active: category === cat,
          }))}
        />
      </FilterBar>

      <h2 className="sr-only">Mods</h2>
      {mods.length === 0 ? (
        <EmptyState icon={Package} title="No mods match" action={<ButtonLink href="/mods/new">Publish one</ButtonLink>}>
          Try another search or category, or be the first to publish one.
        </EmptyState>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {mods.map((mod) => (
            <ModCard key={mod.id} mod={mod} href={`/mods/${mod.slug}`} />
          ))}
        </div>
      )}
    </PageShell>
  );
}
