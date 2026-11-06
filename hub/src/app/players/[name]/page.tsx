import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft, Swords } from "lucide-react";
import { getCloudflareContext } from "@opennextjs/cloudflare";

import { Footer } from "../../components/Footer";
import { Navbar } from "../../components/Navbar";
import { EmptyState, PageHeader, PageShell, Pager } from "../../components/ui";
import { listMatches, playerTotals } from "@/lib/api/matches";
import { nameAccount, playerMapMarks, playerRecord } from "@/lib/api/player-record";
import { parseMapCode } from "@/lib/filters";
import { PlayerRecordView } from "../_components/PlayerRecordView";

/**
 * A player's public record, by the name the game gave them. Names are not
 * identities: two people can share one, and one person can change theirs.
 * A seat its player claimed from their own game also shows on their hub
 * profile, which is the record ranking will use.
 */
export const dynamic = "force-dynamic";

export async function generateMetadata({ params }: { params: Promise<{ name: string }> }): Promise<Metadata> {
  const name = decodeURIComponent((await params).name);
  return {
    title: `${name} · Combat record | MJOLNIR Core`,
    description: `${name}'s public Halo Campaign Evolved multiplayer record: K/D, weapons, medals, rivals and where they fight.`,
  };
}

export default async function PlayerPage({
  params,
  searchParams,
}: {
  params: Promise<{ name: string }>;
  searchParams: Promise<{ before?: string; map?: string }>;
}) {
  const name = decodeURIComponent((await params).name).slice(0, 64);
  const { before: rawBefore, map: rawMap } = await searchParams;
  const before = /^[\d\- :]{10,19}$/.test(rawBefore ?? "") ? rawBefore : undefined;
  const { env } = getCloudflareContext();
  const db = env.DB as never;
  const [totals, record, account, { matches, next }] = await Promise.all([
    playerTotals(db, { name }),
    playerRecord(db, { name }),
    nameAccount(db, name),
    listMatches(db, { player: name, before }),
  ]);
  const base = `/players/${encodeURIComponent(name)}`;
  const href = (b?: string) => `${base}${b ? `?before=${encodeURIComponent(b)}` : ""}#matches`;

  if (totals.matches === 0) {
    return (
      <PageShell>
        <PageHeader back={{ href: "/matches", label: "Match history" }} eyebrow="Player" title={name} />
        <EmptyState icon={Swords} title="No matches under this name">
          Public games report each match when it ends; this name has not finished one yet.
        </EmptyState>
      </PageShell>
    );
  }

  const mapCode = parseMapCode(rawMap) ?? record.maps[0]?.code ?? null;
  const marks = mapCode ? await playerMapMarks(db, { name }, mapCode) : [];

  return (
    <>
      <Navbar />
      <main id="main">
        <PlayerRecordView
          standalone
          name={name}
          avatar={account}
          totals={totals}
          record={record}
          marks={marks}
          mapCode={mapCode}
          mapHref={(code) => `${base}?map=${code}`}
          matches={matches}
          matchesFooter={<Pager newest={before ? href() : undefined} older={next ? href(next) : undefined} />}
          aside={
            <div className="mb-6 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-text-muted">
              <Link href="/matches" className="inline-flex items-center gap-1.5 hover:text-foreground">
                <ArrowLeft aria-hidden className="h-4 w-4" />
                Match history
              </Link>
              {account && (
                <Link href={`/users/${account.id}`} className="hover:text-foreground">
                  Hub profile: <span className="text-foreground">{account.name}</span>
                </Link>
              )}
            </div>
          }
          note={
            <>
              Public matches played under this name, as their hosts reported them. Anyone can play under any name;
              matches linked to a hub account are on that account&apos;s profile.
            </>
          }
        />
      </main>
      <Footer />
    </>
  );
}
