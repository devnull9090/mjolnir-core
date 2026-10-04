import Link from "next/link";
import type { Metadata } from "next";
import { getCloudflareContext } from "@opennextjs/cloudflare";

import { Navbar } from "../../components/Navbar";
import { Footer } from "../../components/Footer";
import { listMatches, playerTotals } from "@/lib/api/matches";
import { MatchTable, PlayerTotalsStrip } from "../../matches/_components/MatchTable";

/**
 * A player's public matches, by the name the game gave them. Names are not
 * identities: two people can share one, and one person can change theirs.
 * A seat its player claimed from their own game also shows on their hub
 * profile, which is the record ranking will use.
 */
export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: { params: Promise<{ name: string }> }): Promise<Metadata> {
  const name = decodeURIComponent((await params).name);
  return {
    title: `${name} · Match history | MJOLNIR Core`,
    description: `${name}'s public Halo Campaign Evolved multiplayer matches: wins, kills and deaths.`,
  };
}

export default async function PlayerPage({
  params,
  searchParams,
}: {
  params: Promise<{ name: string }>;
  searchParams: Promise<{ before?: string }>;
}) {
  const name = decodeURIComponent((await params).name).slice(0, 64);
  const { before: rawBefore } = await searchParams;
  const before = /^[\d\- :]{10,19}$/.test(rawBefore ?? "") ? rawBefore : undefined;
  const { env } = getCloudflareContext();
  const db = env.DB as never;
  const [totals, { matches, next }] = await Promise.all([
    playerTotals(db, { name }),
    listMatches(db, { player: name, before }),
  ]);
  const href = (b?: string) => `/players/${encodeURIComponent(name)}${b ? `?before=${encodeURIComponent(b)}` : ""}`;

  return (
    <>
      <Navbar />

      <main className="pt-32 md:pt-36 pb-16 px-6 max-w-6xl mx-auto">
        <Link href="/matches" className="text-xs text-text-dim hover:text-foreground">← Match history</Link>
        <h1 className="mt-2 mb-2 text-3xl md:text-4xl font-black text-foreground break-words">{name}</h1>
        <p className="mb-6 text-sm text-text-muted max-w-2xl">
          Public matches played under this name{totals.last_played ? "" : ": none yet"}. Anyone can
          play under any name; matches linked to a hub account are on that account&apos;s profile.
        </p>

        {totals.matches > 0 && (
          <section className="mb-10">
            <PlayerTotalsStrip totals={totals} />
          </section>
        )}

        <section>
          <h2 className="text-sm font-bold uppercase text-text-dim mb-3">Matches</h2>
          <MatchTable matches={matches} seat />
          {(before || next) && (
            <div className="mt-6 flex gap-4 text-sm">
              {before && <Link href={href()} className="text-text-muted hover:text-foreground">← Newest</Link>}
              {next && <Link href={href(next)} className="text-gold hover:underline">Older →</Link>}
            </div>
          )}
        </section>
      </main>

      <Footer />
    </>
  );
}
