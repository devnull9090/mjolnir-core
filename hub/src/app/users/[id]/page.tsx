import { cache } from "react";
import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { getCloudflareContext } from "@opennextjs/cloudflare";
// Module imports, not the barrel: this page renders on the server, and the
// barrel would drag the kit's React context into a Server Component graph.
// ProfileSummary is hook-free for exactly this reason.
import { ProfileSummary } from "@mjolnir/hub-kit/ui/ProfileSummary";
import { formatCount } from "@mjolnir/hub-kit/ui/format";

import { Package } from "lucide-react";

import { ModCard } from "../../components/HubKit";
import { EmptyState, PageShell, SectionHeading } from "../../components/ui";
import { getUserProfile } from "@/lib/api/queries";
import { listMatches, playerTotals } from "@/lib/api/matches";
import { playerMapMarks, playerRecord } from "@/lib/api/player-record";
import { parseMapCode } from "@/lib/filters";
import { PlayerTotalsStrip } from "../../matches/_components/MatchTable";
import { PlayerRecordView } from "../../players/_components/PlayerRecordView";

/**
 * A public profile: who someone is here, and what they have done.
 *
 * Routed by user id rather than by name. Discord usernames are not unique in
 * `users` — nothing stops a released handle being re-registered by another
 * account — and a URL that can go ambiguous is not one to hang a page on.
 *
 * What the page shows is counts, in both directions: what their published
 * work drew, and what they have contributed and installed. It deliberately
 * never lists *which* mods they downloaded — nobody publishes their library
 * by signing in — and no API route serves that either.
 *
 * The head and the figures come from <ProfileSummary>, which the launcher
 * renders too. Only the mods grid is this page's own, because a card here is
 * a link and a card in the launcher opens an install pane.
 */
const loadProfile = cache((id: string) => {
  const { env } = getCloudflareContext();
  return getUserProfile(env.DB as never, id);
});

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  const profile = await loadProfile(id);
  if (!profile) return { title: "Profile | MJOLNIR Core" };

  const name = profile.user.display_name ?? profile.user.username;
  const { mods_published, downloads_received } = profile.stats;
  const description =
    mods_published > 0
      ? `${name} has published ${mods_published} mod${mods_published === 1 ? "" : "s"} for Halo Campaign Evolved, downloaded ${formatCount(downloads_received)} times.`
      : `${name} on MJOLNIR Core.`;

  return {
    title: `${name} | MJOLNIR Core`,
    description,
    alternates: { canonical: `/users/${profile.user.id}` },
    openGraph: {
      title: name,
      description,
      url: `/users/${profile.user.id}`,
      siteName: "MJOLNIR Core",
      type: "profile",
      images: profile.user.avatar_url ? [{ url: profile.user.avatar_url }] : undefined,
    },
    twitter: {
      card: "summary",
      title: name,
      description,
      images: profile.user.avatar_url ? [profile.user.avatar_url] : undefined,
    },
  };
}

export default async function UserProfilePage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ map?: string }>;
}) {
  const { id } = await params;
  const { map: rawMap } = await searchParams;
  const profile = await loadProfile(id);
  // Banned accounts read as absent, exactly as GET /api/v1/users/{id} does.
  if (!profile) notFound();
  const { user, mods } = profile;
  const name = user.display_name ?? user.username;
  // Public matches whose seat this account claimed from its own game (or
  // hosted): docs/match_stats.md.
  const { env } = getCloudflareContext();
  const db = env.DB as never;
  const [totals, record, { matches }] = await Promise.all([
    playerTotals(db, { user: user.id }),
    playerRecord(db, { user: user.id }),
    listMatches(db, { user: user.id, limit: 9 }),
  ]);
  const mapCode = parseMapCode(rawMap) ?? record.maps[0]?.code ?? null;
  const marks = mapCode ? await playerMapMarks(db, { user: user.id }, mapCode) : [];

  return (
    <PageShell width="6xl">
      <ProfileSummary profile={profile} />

      {totals.matches > 0 ? (
        <section aria-label="Multiplayer" className="mt-12">
          <PlayerRecordView
            standalone={false}
            name={name}
            avatar={user}
            totals={totals}
            record={record}
            marks={marks}
            mapCode={mapCode}
            mapHref={(code) => `/users/${user.id}?map=${code}`}
            matches={matches}
            reports={profile.stats.player_reports}
          />
        </section>
      ) : (
        profile.stats.player_reports > 0 && (
          <section aria-labelledby="multiplayer" className="mt-12">
            <SectionHeading id="multiplayer">Multiplayer</SectionHeading>
            <PlayerTotalsStrip totals={totals} reports={profile.stats.player_reports} />
          </section>
        )
      )}

      <section aria-labelledby="mods" className="mt-12">
        <SectionHeading id="mods">Mods{mods.length > 0 ? ` · ${mods.length}` : ""}</SectionHeading>
        {mods.length === 0 ? (
          <EmptyState icon={Package} title="Nothing published yet">
            When {name} publishes a mod it will show up here.
          </EmptyState>
        ) : (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            {mods.map((mod) => (
              <ModCard key={mod.id} mod={mod} href={`/mods/${mod.slug}`} />
            ))}
          </div>
        )}
      </section>
    </PageShell>
  );
}
