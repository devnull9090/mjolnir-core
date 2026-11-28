import Link from "next/link";
import { ArrowRight, CheckCircle2, Download, ExternalLink, Radio, Swords } from "lucide-react";

import { Navbar } from "../components/Navbar";
import { Footer } from "../components/Footer";
import { CommunityCallout, MultiplayerFaq, PlaySteps } from "../components/MultiplayerMarketing";
import { Reveal, SpotlightCard } from "../components/Motion";
import { ClassicMapsGrid, type RosterMap } from "../components/ClassicMapsGrid";
import { LobbyCard } from "../components/LobbyCard";
import { MatchCard } from "../matches/_components/MatchCard";
import { getLandingData } from "@/lib/landing-data";
import {
  CLASSIC_MAPS,
  MULTIPLAYER_FAQS,
  MULTIPLAYER_IMAGES,
  MULTIPLAYER_PATH,
  MULTIPLAYER_RELEASE_PATH,
  SITE_URL,
  marketingMetadata,
} from "@/lib/marketing";
import { GAME_TYPE_NAMES } from "@/kit/types";

export const metadata = marketingMetadata(
  "Halo Campaign Evolved Multiplayer Mod, Maps & FAQ | MJOLNIR",
  "Does Halo Campaign Evolved have multiplayer? Yes, with MJOLNIR Core. Play Slayer and CTF on all 19 classic Halo CE maps. Get setup steps, requirements, and FAQs.",
  MULTIPLAYER_PATH,
);

// Pulls live lobbies, recent matches and the current map catalog from D1.
export const dynamic = "force-dynamic";

const faqSchema = {
  "@context": "https://schema.org",
  "@type": "FAQPage",
  "@id": SITE_URL + MULTIPLAYER_PATH + "#faq",
  mainEntity: MULTIPLAYER_FAQS.map((faq) => ({
    "@type": "Question",
    name: faq.question,
    acceptedAnswer: { "@type": "Answer", text: faq.answer },
  })),
};

export default async function MultiplayerPage() {
  const data = await getLandingData();

  const rosterMaps: RosterMap[] =
    data.maps.length > 0
      ? data.maps.map((m) => ({
          name: m.title,
          slug: m.slug,
          code: m.code,
          coverUrl: m.cover_url,
          modes: m.modes.map((mode) => GAME_TYPE_NAMES[mode] ?? mode),
          group: !m.official ? "community" : m.game === "halo2" ? "halo2" : "halo1",
        }))
      : CLASSIC_MAPS.map((m) => ({
          name: m.name,
          slug: m.slug,
          code: null,
          coverUrl: null,
          modes: ["Slayer", "Capture the Flag"],
          group: "halo1" as const,
        }));

  const hasLiveOrMatches = data.lobbies.length > 0 || data.recentMatches.length > 0;

  return (
    <>
      <Navbar />
      <main id="main" className="marketing">
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(faqSchema).replace(/</g, "\\u003c") }}
        />

        {/* ── Hero ──────────────────────────────────────────────────── */}
        <section className="relative isolate overflow-hidden border-b border-border px-6 pb-16 pt-40 md:pt-48">
          <div
            aria-hidden="true"
            className="mj-grid-bg pointer-events-none absolute inset-0 -z-10 opacity-45 [mask-image:radial-gradient(ellipse_75%_65%_at_65%_30%,black,transparent_85%)]"
          />
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-96 bg-[radial-gradient(ellipse_65%_50%_at_70%_0%,#d4a84318,transparent_70%)]"
          />

          <div className="mx-auto grid max-w-6xl items-center gap-10 lg:grid-cols-[1.1fr_1fr]">
            <div>
              <div className="mj-rise">
                {data.lobbies.length > 0 ? (
                  <Link
                    href="/games"
                    className="inline-flex items-center gap-2 rounded-full border border-accent-green/35 bg-accent-green/10 px-3 py-1 font-mono text-[11px] font-semibold uppercase tracking-[0.16em] text-accent-green hover:bg-accent-green/20 transition-colors"
                  >
                    <span className="relative flex size-2 items-center justify-center" aria-hidden="true">
                      <span className="mj-live-ring absolute inline-flex size-full rounded-full bg-accent-green" />
                      <span className="relative inline-flex size-1.5 rounded-full bg-accent-green" />
                    </span>
                    {data.lobbies.length} live game{data.lobbies.length === 1 ? "" : "s"} ·{" "}
                    {data.livePlayers} player{data.livePlayers === 1 ? "" : "s"} online
                  </Link>
                ) : (
                  <p className="marketing-eyebrow">MJOLNIR Core / Multiplayer alpha</p>
                )}
              </div>

              <h1 className="mj-rise mj-rise-d1 mt-5 text-4xl font-black leading-[1.06] tracking-tight sm:text-5xl lg:text-6xl">
                Halo Campaign Evolved.
                <br />
                <span className="bg-gradient-to-r from-[#f0ca69] via-gold to-[#c49230] bg-clip-text text-transparent">
                  Now with classic multiplayer.
                </span>
              </h1>
              <p className="mj-rise mj-rise-d2 mt-6 text-lg leading-8 text-text-muted">
                Looking for Campaign Evolved multiplayer? MJOLNIR Core is the community-made modding
                framework that brings Slayer, Capture the Flag, Forge, and all 19 classic Halo CE maps
                to your game.
              </p>
              <div className="mj-rise mj-rise-d3 mt-8 flex flex-col gap-3 sm:flex-row">
                <Link href="/download" className="marketing-button-primary">
                  <Download aria-hidden="true" className="size-4" /> Get the multiplayer launcher
                </Link>
                <a href="#setup" className="marketing-button-secondary">
                  How to play <ArrowRight aria-hidden="true" className="size-4" />
                </a>
              </div>
              <p className="mj-rise mj-rise-d4 mt-5 text-xs leading-6 text-text-muted">
                Community mod · Free &amp; open source · Your own copy of the game required
              </p>
            </div>

            <figure className="mj-rise mj-rise-d3 mj-hud-corners rounded-xl border border-border-bright bg-surface p-3 shadow-[0_24px_56px_-28px_rgba(0,0,0,0.9)]">
              <div className="overflow-hidden rounded-lg">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={MULTIPLAYER_IMAGES.bloodGulch}
                  alt="Blood Gulch running in Halo Campaign Evolved through MJOLNIR Core"
                  fetchPriority="high"
                  width={960}
                  height={720}
                  className="aspect-[4/3] w-full object-cover transition-transform duration-700 hover:scale-[1.03]"
                />
              </div>
              <figcaption className="flex items-center justify-between gap-2 px-2 pb-1.5 pt-4 font-mono text-[10px] uppercase tracking-widest text-text-muted">
                <span>Blood Gulch / Captured in Campaign Evolved</span>
                <span className="text-gold">Up to 16 players</span>
              </figcaption>
            </figure>
          </div>
        </section>

        {/* ── Direct answer & Alpha brief ───────────────────────────── */}
        <section className="mx-auto max-w-6xl px-6 py-16 md:py-20">
          <Reveal>
            <div className="grid gap-10 lg:grid-cols-[1.1fr_1fr] lg:gap-16">
              <div>
                <p className="marketing-eyebrow">The answer you came for</p>
                <h2 className="mt-4 text-3xl font-black tracking-tight sm:text-4xl">
                  Does Halo Campaign Evolved have multiplayer?
                </h2>
                <p className="mt-5 text-lg leading-8">
                  <strong className="text-gold">With MJOLNIR Core, it does.</strong> Install our
                  multiplayer mod to play classic competitive Halo with your friends inside Campaign
                  Evolved.
                </p>
                <p className="mt-4 leading-7 text-text-muted">
                  Get the original maps, a multiplayer lobby, a browser for public games, match chat,
                  a kill feed, a scoreboard, team-aware HUD elements, and public match history with 3D
                  kill replays on the hub. Slayer and CTF are available across the classic collection,
                  with framework support for Team Slayer, King of the Hill, Oddball, Race, and Forge.
                </p>
              </div>
              <SpotlightCard className="rounded-xl border border-gold/25 bg-surface p-6 sm:p-8">
                <aside className="relative z-[2]">
                  <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.18em] text-gold">
                    Alpha briefing
                  </p>
                  <h3 className="mt-2 text-lg font-bold text-foreground">What to know before dropping in</h3>
                  <ul className="mt-5 space-y-3 text-sm leading-6 text-text-muted">
                    {[
                      "Up to 16 players in a fireteam, each on their own PC.",
                      "Works on Windows with both Steam and Game Pass — and the two play together seamlessly.",
                      "Missing a map your host picked? Download it right inside the game with no restart.",
                      "Community-made multiplayer, separate from official campaign and co-op features.",
                    ].map((point) => (
                      <li key={point} className="flex items-start gap-2.5">
                        <CheckCircle2 aria-hidden="true" className="mt-1 size-4 shrink-0 text-gold" />
                        <span>{point}</span>
                      </li>
                    ))}
                  </ul>
                  <Link
                    href={MULTIPLAYER_RELEASE_PATH}
                    className="mt-6 inline-flex items-center gap-2 text-sm font-semibold text-gold hover:underline"
                  >
                    Read the alpha announcement <ArrowRight aria-hidden="true" className="size-4" />
                  </Link>
                </aside>
              </SpotlightCard>
            </div>
          </Reveal>
        </section>

        {/* ── Live lobbies & recent matches (when present in D1) ────── */}
        {hasLiveOrMatches && (
          <section className="border-t border-border bg-surface/50 px-6 py-16 md:py-20">
            <div className="mx-auto max-w-6xl space-y-10">
              {data.lobbies.length > 0 && (
                <Reveal>
                  <div className="mb-4 flex flex-wrap items-center justify-between gap-4">
                    <h2 className="inline-flex items-center gap-2 font-mono text-xs font-semibold uppercase tracking-[0.16em] text-accent-green">
                      <Radio aria-hidden="true" className="size-4" />
                      Active public lobbies right now
                    </h2>
                    <Link href="/games" className="inline-flex items-center gap-1.5 text-sm font-semibold text-gold hover:underline">
                      Open live game browser <ArrowRight aria-hidden="true" className="size-4" />
                    </Link>
                  </div>
                  <ul className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                    {data.lobbies.slice(0, 2).map((lobby) => (
                      <li key={lobby.id} className="flex">
                        <LobbyCard lobby={lobby} coverUrl={data.coversByCode.get(lobby.map_code) ?? null} />
                      </li>
                    ))}
                  </ul>
                </Reveal>
              )}

              {data.recentMatches.length > 0 && (
                <Reveal delay={60}>
                  <div className="mb-4 flex flex-wrap items-center justify-between gap-4">
                    <h2 className="inline-flex items-center gap-2 font-mono text-xs font-semibold uppercase tracking-[0.16em] text-text-muted">
                      <Swords aria-hidden="true" className="size-4 text-gold" />
                      Recent public matches
                    </h2>
                    <Link href="/matches" className="inline-flex items-center gap-1.5 text-sm font-semibold text-gold hover:underline">
                      Browse full match history <ArrowRight aria-hidden="true" className="size-4" />
                    </Link>
                  </div>
                  <ul className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
                    {data.recentMatches.map((match) => (
                      <li key={match.id} className="flex">
                        <MatchCard match={match} />
                      </li>
                    ))}
                  </ul>
                </Reveal>
              )}
            </div>
          </section>
        )}

        {/* ── Setup Steps ───────────────────────────────────────────── */}
        <section id="setup" className="scroll-mt-32 border-y border-border bg-surface px-6 py-16 md:py-20">
          <div className="mx-auto max-w-6xl">
            <Reveal>
              <p className="marketing-eyebrow">From download to drop-in</p>
              <h2 className="mb-10 mt-4 text-3xl font-black tracking-tight md:text-4xl">
                How to play Campaign Evolved multiplayer
              </h2>
            </Reveal>
            <PlaySteps />
            <div className="mt-8 flex flex-wrap gap-6 text-sm font-semibold text-gold">
              <Link href="/download" className="inline-flex items-center gap-2 hover:underline">
                Download &amp; requirements <ArrowRight aria-hidden="true" className="size-4" />
              </Link>
              <Link href="/games" className="inline-flex items-center gap-2 hover:underline">
                View live games <ArrowRight aria-hidden="true" className="size-4" />
              </Link>
              <Link href="/matches" className="inline-flex items-center gap-2 text-text-muted hover:text-foreground">
                Match history <ArrowRight aria-hidden="true" className="size-4" />
              </Link>
            </div>
          </div>
        </section>

        {/* ── Visual Map Collection ─────────────────────────────────── */}
        <section className="mx-auto max-w-6xl px-6 py-16 md:py-24">
          <Reveal>
            <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
              <div>
                <p className="marketing-eyebrow">The full collection</p>
                <h2 className="mt-4 text-3xl font-black tracking-tight md:text-4xl">
                  All 19 original Halo CE maps — and growing.
                </h2>
                <p className="mt-4 max-w-2xl leading-7 text-text-muted">
                  The original Xbox arenas, Halo PC additions, Halo 2 classics, and custom community
                  worlds together in Campaign Evolved. Install the collection in one click from the
                  launcher, or inspect any map below.
                </p>
              </div>
              <Link href="/maps" className="inline-flex shrink-0 items-center gap-2 text-sm font-semibold text-gold hover:underline">
                Full map catalog &amp; filters <ArrowRight aria-hidden="true" className="size-4" />
              </Link>
            </div>

            <ClassicMapsGrid maps={rosterMaps} />
          </Reveal>
        </section>

        {/* ── Creator Framework ─────────────────────────────────────── */}
        <section className="border-y border-border bg-surface px-6 py-16 md:py-20">
          <Reveal className="mx-auto grid max-w-6xl gap-8 md:grid-cols-2 md:gap-16">
            <div>
              <p className="marketing-eyebrow">A framework to build on</p>
              <h2 className="mt-4 text-3xl font-black tracking-tight">Make custom maps and content.</h2>
              <p className="mt-5 leading-7 text-text-muted">
                Use the Blender addon, custom level pipeline, Forge packs, tag editor, and CLI to
                build your own worlds and change the way they play. Start with a weapon or texture
                edit, then work toward a map of your own.
              </p>
            </div>
            <div className="flex flex-col justify-center gap-3">
              {[
                { href: "/docs/guides/level-authoring", label: "Create a custom level" },
                { href: "/docs/notes/ce-map-conversion", label: "Explore classic map conversion" },
                { href: "/docs/guides/making-your-first-mod", label: "Make your first content mod" },
                { href: "/docs/notes/map-distribution", label: "Package and publish a map" },
              ].map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="group flex items-center justify-between gap-4 rounded-lg border border-border bg-background/55 px-4 py-3.5 text-sm font-semibold text-gold transition-all hover:border-gold/45 hover:bg-surface-raised hover:text-foreground"
                >
                  <span>{item.label}</span>
                  <ExternalLink aria-hidden="true" className="size-4 shrink-0 transition-transform group-hover:translate-x-0.5" />
                </Link>
              ))}
            </div>
          </Reveal>
        </section>

        {/* ── FAQ ───────────────────────────────────────────────────── */}
        <section id="faq" className="mx-auto max-w-4xl scroll-mt-32 px-6 py-16 md:py-24">
          <Reveal>
            <p className="marketing-eyebrow">Before your first match</p>
            <h2 className="mb-9 mt-4 text-3xl font-black tracking-tight md:text-4xl">
              Campaign Evolved multiplayer FAQ
            </h2>
            <MultiplayerFaq />
          </Reveal>
        </section>

        <CommunityCallout />
      </main>
      <Footer />
    </>
  );
}
