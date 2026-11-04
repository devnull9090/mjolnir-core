import type { Metadata } from "next";
import { Blocks, Plus, Search } from "lucide-react";
import { getCloudflareContext } from "@opennextjs/cloudflare";
import { ModCard } from "../components/HubKit";
import { ButtonLink, EmptyState, FilterBar, PageHeader, PageShell, SelectNav } from "../components/ui";
import { listPublishedMods } from "@/lib/api/queries";

export const metadata: Metadata = {
  title: "Forge packs | MJOLNIR Core",
  description: "Community model packs for building Halo Campaign Evolved Forge levels: platforms, blocks, ramps, walls and more.",
};

const SORTS = [
  { key: "newest", label: "Newest" },
  { key: "downloads", label: "Most downloaded" },
  { key: "rating", label: "Top rated" },
] as const;

export default async function ForgePacksPage({ searchParams }: {
  searchParams: Promise<{ q?: string; sort?: string }>;
}) {
  const params = await searchParams;
  const q = params.q?.trim() || undefined;
  const sort = SORTS.find((s) => s.key === params.sort)?.key ?? "newest";
  const { env } = getCloudflareContext();
  const mods = await listPublishedMods(env.DB as never, { q, sort, forge: true });

  return (
    <PageShell>
      <PageHeader
        eyebrow="Community workshop"
        title="Forge packs"
        description="Build with community-made platforms, blocks, ramps, walls and cover. Download a pack through the launcher, then use its models in compatible Forge levels."
        actions={<ButtonLink href="/mods/new"><Plus aria-hidden className="h-4 w-4" />Publish a pack</ButtonLink>}
      />
      <FilterBar>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <form action="/forge" method="get" role="search" className="relative sm:w-72">
            <label htmlFor="forge-search" className="sr-only">Search Forge packs</label>
            <Search aria-hidden className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-muted" />
            <input id="forge-search" type="search" name="q" defaultValue={q ?? ""} placeholder="Search Forge packs…"
              className="min-h-10 w-full rounded-lg border border-border bg-surface-raised pl-9 pr-3 text-sm text-foreground placeholder:text-text-muted hover:border-border-bright focus:border-gold/60" />
            {sort !== "newest" && <input type="hidden" name="sort" value={sort} />}
          </form>
          <SelectNav label="Sort" name="sort" value={sort} action="/forge" hidden={{ q }} options={SORTS.map((s) => ({
            value: s.key, label: s.label,
            href: `/forge?${new URLSearchParams({ ...(q ? { q } : {}), sort: s.key })}`,
          }))} />
        </div>
      </FilterBar>
      {mods.length === 0 ? (
        <EmptyState icon={Blocks} title={q ? "No packs match" : "The workshop is open"}
          action={<ButtonLink href="/mods/new">Publish a Forge pack</ButtonLink>}>
          {q ? "Try another search." : "Share a set of modular pieces for the community to build with."}
        </EmptyState>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {mods.map((mod) => <ModCard key={mod.id} mod={mod} href={`/mods/${mod.slug}`} />)}
        </div>
      )}
    </PageShell>
  );
}
