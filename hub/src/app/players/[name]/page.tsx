import type { Metadata } from "next";
import { Swords } from "lucide-react";
import { getCloudflareContext } from "@opennextjs/cloudflare";

import { EmptyState, PageHeader, PageShell, Pager, PlayerAvatar, SectionHeading } from "../../components/ui";
import { listMatches, playerTotals } from "@/lib/api/matches";
import { MatchGrid } from "../../matches/_components/MatchCard";
import { PlayerTotalsStrip } from "../../matches/_components/MatchTable";

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
    <PageShell>
      <PageHeader
        back={{ href: "/matches", label: "Match history" }}
        eyebrow="Player"
        title={
          <span className="flex items-center gap-4">
            <PlayerAvatar name={name} user={null} size="lg" />
            <span className="min-w-0 break-words">{name}</span>
          </span>
        }
        description={
          <>
            Public matches played under this name{totals.last_played ? "" : ": none yet"}. Anyone can play under any
            name; matches linked to a hub account are on that account&apos;s profile.
          </>
        }
      />

      {totals.matches > 0 && (
        <section aria-labelledby="career" className="mb-12">
          <SectionHeading id="career">Career</SectionHeading>
          <PlayerTotalsStrip totals={totals} />
        </section>
      )}

      <section aria-labelledby="matches">
        <SectionHeading id="matches">Matches</SectionHeading>
        {matches.length === 0 ? (
          <EmptyState icon={Swords} title="No matches under this name">
            Public games report each match when it ends; this name has not finished one yet.
          </EmptyState>
        ) : (
          <MatchGrid matches={matches} />
        )}
        <Pager newest={before ? href() : undefined} older={next ? href(next) : undefined} />
      </section>
    </PageShell>
  );
}
