import Link from "next/link";
import type { Metadata } from "next";
import { Plus, Search } from "lucide-react";
import { getCloudflareContext } from "@opennextjs/cloudflare";

import { Navbar } from "../components/Navbar";
import { Footer } from "../components/Footer";
import { ModCard } from "../components/HubKit";
import { listPublishedMods } from "@/lib/api/queries";

export const metadata: Metadata = {
  title: "Mods | MJOLNIR Core",
  description: "Browse and download community mods for Halo Campaign Evolved.",
};

const CATEGORIES = ["all", "gameplay", "maps", "textures", "weapons", "camera", "tools", "framework", "multiplayer"];
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
  const mods = await listPublishedMods(env.DB as never, { q, category, sort });

  const qs = (over: Record<string, string>) => {
    const merged = { q: q ?? "", category, sort, ...over };
    const u = new URLSearchParams();
    for (const [k, v] of Object.entries(merged)) if (v && v !== "all" && v !== "newest") u.set(k, v);
    const s = u.toString();
    return s ? `/mods?${s}` : "/mods";
  };

  return (
    <>
      <Navbar />

      <main className="pt-32 md:pt-36 pb-16 px-6 max-w-6xl mx-auto">
        <div className="mb-10 flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-4xl font-black text-foreground mb-3">Mods</h1>
            <p className="text-text-muted text-lg">
              Browse and download community mods for Halo Campaign Evolved
            </p>
          </div>
          <Link
            href="/mods/new"
            className="flex items-center gap-2 px-4 py-2 text-sm font-semibold rounded-lg bg-gold text-background hover:brightness-110 transition-all"
          >
            <Plus className="w-4 h-4" />
            Publish a mod
          </Link>
        </div>

        {/* Search + sort */}
        <form action="/mods" method="get" className="mb-6 flex flex-wrap items-center gap-3">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-dim" />
            <input
              type="search"
              name="q"
              defaultValue={q ?? ""}
              placeholder="Search mods…"
              className="pl-9 pr-3 py-2 text-sm rounded-lg bg-background border border-border text-foreground placeholder:text-text-dim focus:border-gold/60 focus:outline-none w-64"
            />
          </div>
          {category !== "all" && <input type="hidden" name="category" value={category} />}
          {sort !== "newest" && <input type="hidden" name="sort" value={sort} />}
          <div className="flex items-center gap-1 text-xs">
            {SORTS.map((s) => (
              <Link
                key={s.key}
                href={qs({ sort: s.key })}
                className={`px-3 py-1.5 rounded-lg border transition-colors ${
                  sort === s.key
                    ? "border-gold/60 text-gold"
                    : "border-border text-text-muted hover:text-foreground"
                }`}
              >
                {s.label}
              </Link>
            ))}
          </div>
        </form>

        {/* Categories */}
        <div className="mb-8 flex gap-2 overflow-x-auto">
          {CATEGORIES.map((cat) => (
            <Link
              key={cat}
              href={qs({ category: cat })}
              className={`shrink-0 px-3 py-1.5 rounded-lg border text-xs font-semibold capitalize transition-colors ${
                category === cat
                  ? "border-gold/60 text-gold"
                  : "border-border text-text-muted hover:text-foreground"
              }`}
            >
              {cat}
            </Link>
          ))}
        </div>

        {mods.length === 0 ? (
          <div className="rounded-xl border border-dashed border-border-bright p-12 text-center">
            <p className="text-foreground font-semibold mb-1">No mods match</p>
            <p className="text-sm text-text-muted">
              Be the first —{" "}
              <Link href="/mods/new" className="text-gold hover:underline">
                publish one
              </Link>
              .
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {mods.map((mod) => (
              <ModCard key={mod.id} mod={mod} href={`/mods/${mod.slug}`} />
            ))}
          </div>
        )}
      </main>

      <Footer />
    </>
  );
}
