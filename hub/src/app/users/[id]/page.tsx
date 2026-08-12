import { cache } from "react";
import Link from "next/link";
import { notFound } from "next/navigation";
import type { Metadata } from "next";
import { getCloudflareContext } from "@opennextjs/cloudflare";
// Module imports, not the barrel: this page renders on the server, and the
// barrel would drag the kit's React context into a Server Component graph.
// ProfileSummary is hook-free for exactly this reason.
import { ProfileSummary } from "@mjolnir/hub-kit/ui/ProfileSummary";
import { formatCount } from "@mjolnir/hub-kit/ui/format";

import { Navbar } from "../../components/Navbar";
import { Footer } from "../../components/Footer";
import { ModCard } from "../../components/HubKit";
import { getUserProfile } from "@/lib/api/queries";

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
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const profile = await loadProfile(id);
  // Banned accounts read as absent, exactly as GET /api/v1/users/{id} does.
  if (!profile) notFound();
  const { user, mods } = profile;
  const name = user.display_name ?? user.username;

  return (
    <>
      <Navbar />

      <main className="pt-32 md:pt-36 pb-16 px-6 max-w-5xl mx-auto">
        <ProfileSummary profile={profile} />

        <section className="mt-8">
          <h2 className="text-sm font-bold uppercase text-text-dim mb-3">
            Mods{mods.length > 0 ? ` · ${mods.length}` : ""}
          </h2>
          {mods.length === 0 ? (
            <div className="rounded-xl border border-dashed border-border-bright p-10 text-center">
              <p className="text-foreground font-semibold mb-1">Nothing published yet</p>
              <p className="text-sm text-text-muted">
                When {name} publishes a mod it will show up here.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {mods.map((mod) => (
                <ModCard key={mod.id} mod={mod} href={`/mods/${mod.slug}`} />
              ))}
            </div>
          )}
        </section>

        <div className="mt-10 text-xs text-text-dim">
          <Link href="/mods" className="hover:text-foreground">
            ← Browse all mods
          </Link>
        </div>
      </main>

      <Footer />
    </>
  );
}
