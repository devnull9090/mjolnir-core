import Link from "next/link";
import {
  ArrowRight,
  Boxes,
  CheckCircle2,
  Compass,
  Download,
  Hammer,
  Radio,
  Swords,
  Upload,
  Wrench,
} from "lucide-react";

import { Navbar } from "../components/Navbar";
import { Footer } from "../components/Footer";
import { CommunityCallout, MultiplayerFaq, PlaySteps } from "../components/MultiplayerMarketing";
import { CountUp, Reveal, SpotlightCard } from "../components/Motion";
import { HeroRotator } from "../components/HeroRotator";
import { MultiplayerShowcase } from "../components/MultiplayerShowcase";
import { ClassicMapsGrid, type RosterMap } from "../components/ClassicMapsGrid";
import { LobbyCard } from "../components/LobbyCard";
import { MatchCard } from "../matches/_components/MatchCard";
import { recordDisplay } from "../players/_components/font";
import { getLandingData } from "@/lib/landing-data";
import {
  CLASSIC_MAPS,
  MULTIPLAYER_FAQS,
  MULTIPLAYER_HERO_SCENES,
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

const PC_MAP_SLUGS = new Set(
  CLASSIC_MAPS.filter((m) => m.origin === "pc").map((m) => m.slug),
);

const CREATOR_GUIDES = [
  {
    icon: Boxes,
    title: "Create a custom level",
    badge: "Blender + Level Pipeline",
    description: "Build geometry, lightmaps, spawns, and collision from scratch.",
    href: "/docs/guides/level-authoring",
  },
  {
    icon: Compass,
    title: "Explore classic map conversion",
    badge: "CE & Halo 2",
    description: "How classic Blam BSPs, skies, and tags translate into Campaign Evolved.",
    href: "/docs/notes/ce-map-conversion",
  },
  {
    icon: Wrench,
    title: "Make your first content mod",
    badge: "Tags & Textures",
    description: "Swap weapon skins, tweak sandbox values, or edit audio with the Tag Editor.",
    href: "/docs/guides/making-your-first-mod",
  },
  {
    icon: Upload,
    title: "Package and publish a map",
    badge: "Hub Distribution",
    description: "Sign map packs with the CLI so players can download them straight in-game.",
    href: "/docs/notes/map-distribution",
  },
];

export default async function MultiplayerPage() {
  const data = await getLandingData();

  const coversBySlug = new Map(data.maps.map((m) => [m.slug, m.cover_url]));
  const heroScenes = MULTIPLAYER_HERO_SCENES.map((scene) => ({
    ...scene,
    // Keep the curated first-person HUD captures as-is; enrich map vistas from D1 when available.
    image: scene.image.startsWith("/blog-images/")
      ? scene.image
      : coversBySlug.get(scene.slug) ?? scene.image,
  }));

  const rosterMaps: RosterMap[] =
    data.maps.length > 0
      ? data.maps.map((m) => {
          const group: RosterMap["group"] = !m.official
            ? "community"
            : m.game === "halo2"
              ? "halo2"
              : "halo1";
          const badge =
            group === "community"
              ? "Community"
              : group === "halo2"
                ? "Halo 2"
                : PC_MAP_SLUGS.has(m.slug)
                  ? "Halo PC"
                  : "Halo CE";
          return {
            name: m.title,
            slug: m.slug,
            code: m.code,
            coverUrl: m.cover_url,
            modes: m.modes.map((mode) => GAME_TYPE_NAMES[mode] ?? mode),
            group,
            badge,
          };
        })
      : CLASSIC_MAPS.map((m) => ({
          name: m.name,
          slug: m.slug,
          code: m.code,
          coverUrl: m.image,
          modes: ["Slayer", "Capture the Flag"],
          group: "halo1" as const,
          badge: m.origin === "pc" ? "Halo PC" : "Halo CE",
        }));

  const mapTotal = Math.max(data.totals.maps, CLASSIC_MAPS.length);
  const hasLiveOrMatches = data.lobbies.length > 0 || data.recentMatches.length > 0;

  return (
    <div className={recordDisplay.variable}>
      <Navbar />
      <main id="main" className="marketing">
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(faqSchema).replace(/</g, "\\u003c") }}
        />

        {/* ── 00 / Full-Bleed Atmospheric Hero ──────────────────────── */}
        <HeroRotator
          scenes={heroScenes}
          bottomLeft={
            <nav aria-label="On this page" className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm font-semibold">
              <a href="#setup" className="text-white transition-colors hover:text-gold">
                How to play
              </a>
              <a href="#maps" className="text-slate-300 transition-colors hover:text-gold">
                All {mapTotal} maps
              </a>
              <a href="#faq" className="text-slate-300 transition-colors hover:text-gold">
                Multiplayer FAQ
              </a>
            </nav>
          }
        >
          <div className="max-w-4xl">
            <div className="mj-rise">
              {data.lobbies.length > 0 ? (
                <Link
                  href="/games"
                  className="inline-flex items-center gap-2.5 rounded-full border border-accent-green/35 bg-background/70 px-3.5 py-1.5 font-mono text-[11px] font-semibold uppercase tracking-[0.16em] text-accent-green backdrop-blur-md transition-colors hover:border-accent-green/65"
                >
                  <span className="relative flex size-2 items-center justify-center" aria-hidden="true">
                    <span className="mj-live-ring absolute inline-flex size-full rounded-full bg-accent-green" />
                    <span className="relative inline-flex size-2 rounded-full bg-accent-green" />
                  </span>
                  Live now · {data.lobbies.length} game{data.lobbies.length === 1 ? "" : "s"} ·{" "}
                  {data.livePlayers} player{data.livePlayers === 1 ? "" : "s"} online
                </Link>
              ) : (
                <Link
                  href={MULTIPLAYER_RELEASE_PATH}
                  className="inline-flex items-center gap-2.5 rounded-full border border-gold/30 bg-background/65 px-3.5 py-1.5 font-mono text-[11px] font-medium uppercase tracking-[0.18em] text-gold backdrop-blur-md transition-colors hover:border-gold/60"
                >
                  <span className="relative flex size-2 items-center justify-center" aria-hidden="true">
                    <span className="mj-live-ring absolute inline-flex size-full rounded-full bg-gold/70" />
                    <span className="relative inline-flex size-1.5 rounded-full bg-gold" />
                  </span>
                  MJOLNIR Core · Multiplayer alpha
                </Link>
              )}
            </div>

            <h1 className="mj-rise mj-rise-d1 mt-6 text-[42px] font-black leading-[1.01] tracking-[-0.05em] sm:text-6xl lg:text-[72px]">
              Halo Campaign Evolved.
              <br />
              Now with{" "}
              <span className="bg-gradient-to-r from-[#f0ca69] via-gold to-[#c49230] bg-clip-text text-transparent">
                classic multiplayer.
              </span>
            </h1>

            <p className="mj-rise mj-rise-d2 mt-6 max-w-xl text-base leading-7 text-slate-200 md:text-lg md:leading-8">
              Looking for Campaign Evolved multiplayer? MJOLNIR Core is the free, open-source mod
              that brings Slayer, CTF, Forge, post-game voting, and all 19 classic Halo CE maps
              straight into your game.
            </p>

            <div className="mj-rise mj-rise-d3 mt-8 flex flex-col gap-3 sm:flex-row">
              <Link href="/download" className="marketing-button-primary">
                <Download aria-hidden="true" className="size-4" /> Get the multiplayer launcher{" "}
                <ArrowRight aria-hidden="true" className="size-4" />
              </Link>
              <a href="#setup" className="marketing-button-secondary">
                How to play <ArrowRight aria-hidden="true" className="size-4" />
              </a>
            </div>

            <p className="mj-rise mj-rise-d4 mt-5 text-xs leading-6 text-slate-300">
              Community mod · Free &amp; open source · Steam &amp; Game Pass crossplay · Your own copy required
            </p>
          </div>
        </HeroRotator>

        {/* ── Kinetic Spec & Live Telemetry Strip ───────────────────── */}
        <div className="border-y border-border bg-surface">
          <div className="mx-auto grid max-w-6xl grid-cols-2 px-6 md:grid-cols-4">
            <a
              href="#maps"
              className="group border-b border-border py-6 pr-4 transition-colors hover:bg-surface-raised/60 md:border-b-0 md:py-7 md:pr-6"
            >
              <p className="record-display text-4xl leading-none text-foreground transition-colors group-hover:text-gold sm:text-5xl">
                <CountUp value={mapTotal} />
              </p>
              <p className="mt-2 font-mono text-[10px] uppercase tracking-[0.16em] text-text-muted">
                Playable multiplayer maps
              </p>
            </a>

            <div className="border-b border-l border-border py-6 pl-5 md:border-b-0 md:py-7 md:pl-6">
              <p className="record-display text-4xl leading-none text-foreground sm:text-5xl">
                16P
              </p>
              <p className="mt-2 font-mono text-[10px] uppercase tracking-[0.16em] text-text-muted">
                Fireteam &amp; lobby cap
              </p>
            </div>

            <div className="py-6 pr-4 md:border-l md:border-border md:py-7 md:pl-6 md:pr-6">
              <p className="record-display text-4xl leading-none text-foreground sm:text-5xl">
                8
              </p>
              <p className="mt-2 font-mono text-[10px] uppercase tracking-[0.16em] text-text-muted">
                Game modes + Forge
              </p>
            </div>

            <Link
              href={data.livePlayers > 0 ? "/games" : data.totals.matches > 0 ? "/matches" : "/games"}
              className="group border-l border-border py-6 pl-5 transition-colors hover:bg-surface-raised/60 md:py-7 md:pl-6"
            >
              <p
                className={`record-display text-4xl leading-none transition-colors sm:text-5xl ${
                  data.livePlayers > 0 ? "text-accent-green" : "text-gold"
                }`}
              >
                {data.livePlayers > 0 ? (
                  <CountUp value={data.livePlayers} />
                ) : data.totals.matches > 0 ? (
                  <CountUp value={data.totals.matches} />
                ) : (
                  "CROSSPLAY"
                )}
              </p>
              <p className="mt-2 font-mono text-[10px] uppercase tracking-[0.16em] text-text-muted">
                {data.livePlayers > 0
                  ? `Playing across ${data.lobbies.length} live game${data.lobbies.length === 1 ? "" : "s"}`
                  : data.totals.matches > 0
                    ? "Public matches logged"
                    : "Steam & Game Pass"}
              </p>
            </Link>
          </div>
        </div>

        {/* ── 01 / The Answer & In-Game Multiplayer Showcase ────────── */}
        <section className="mx-auto max-w-6xl px-6 py-20 md:py-28">
          <Reveal>
            <div className="flex flex-col justify-between gap-6 lg:flex-row lg:items-end">
              <div className="max-w-2xl">
                <p className="marketing-eyebrow">01 / The answer you came for</p>
                <h2 className="mt-4 text-3xl font-black tracking-tight sm:text-4xl md:text-5xl">
                  Does Halo Campaign Evolved have multiplayer?
                </h2>
                <p className="mt-5 text-lg leading-8 text-slate-200">
                  <strong className="text-gold">With MJOLNIR Core, it does.</strong> Install the
                  multiplayer mod to play classic competitive Halo with your friends inside Campaign
                  Evolved — complete with native menus, match voting, HUD, and live hub stats.
                </p>
              </div>
              <Link
                href={MULTIPLAYER_RELEASE_PATH}
                className="inline-flex shrink-0 items-center gap-2 text-sm font-semibold text-gold hover:underline"
              >
                Read the alpha announcement <ArrowRight aria-hidden="true" className="size-4" />
              </Link>
            </div>
          </Reveal>

          <Reveal delay={60}>
            <MultiplayerShowcase />
          </Reveal>

          {/* Compact alpha checklist strip */}
          <Reveal delay={90}>
            <ul className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              {[
                "Up to 16 players per match, each on their own Windows PC.",
                "Steam & Xbox app / Game Pass players join the same lobbies.",
                "Missing a host's hub map? Download it in-game with no restart.",
                "Community-made & open source, separate from official co-op.",
              ].map((point) => (
                <li
                  key={point}
                  className="flex items-start gap-2.5 rounded-xl border border-border bg-surface/65 px-4 py-3.5 text-xs leading-5 text-text-muted"
                >
                  <CheckCircle2 aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-gold" />
                  <span>{point}</span>
                </li>
              ))}
            </ul>
          </Reveal>
        </section>

        {/* ── Live lobbies & recent matches (when present in D1) ────── */}
        {hasLiveOrMatches && (
          <section className="relative border-t border-border bg-surface/60 px-6 py-16 md:py-20">
            <div
              aria-hidden="true"
              className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-gold/35 to-transparent"
            />
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
                <Reveal delay={50}>
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

        {/* ── 02 / Setup Steps ──────────────────────────────────────── */}
        <section id="setup" className="scroll-mt-32 border-y border-border bg-surface px-6 py-20 md:py-24">
          <div className="mx-auto max-w-6xl">
            <Reveal>
              <div className="mb-10 flex flex-wrap items-end justify-between gap-6">
                <div>
                  <p className="marketing-eyebrow">02 / From download to drop-in</p>
                  <h2 className="mt-4 text-3xl font-black tracking-tight md:text-4xl">
                    How to play Campaign Evolved multiplayer.
                  </h2>
                </div>
                <Link href="/download" className="marketing-button-primary">
                  Get the launcher <Download aria-hidden="true" className="size-4" />
                </Link>
              </div>
            </Reveal>

            <PlaySteps />

            <div className="mt-8 flex flex-wrap items-center gap-3">
              {[
                { href: "/download", label: "Download & requirements" },
                { href: "/games", label: "Browse live games" },
                { href: "/matches", label: "Match history & 3D kill maps" },
              ].map((link) => (
                <Link
                  key={link.href}
                  href={link.href}
                  className="inline-flex items-center gap-2 rounded-lg border border-border bg-background/60 px-3.5 py-2 text-xs font-semibold text-slate-200 transition-colors hover:border-gold/50 hover:text-gold"
                >
                  {link.label} <ArrowRight aria-hidden="true" className="size-3.5 text-gold" />
                </Link>
              ))}
            </div>
          </div>
        </section>

        {/* ── 03 / Visual Map Collection ────────────────────────────── */}
        <section id="maps" className="scroll-mt-28 mx-auto max-w-6xl px-6 py-20 md:py-28">
          <Reveal>
            <div className="flex flex-col justify-between gap-6 md:flex-row md:items-end">
              <div>
                <p className="marketing-eyebrow">03 / The full collection</p>
                <h2 className="mt-4 text-3xl font-black tracking-tight md:text-5xl">
                  All 19 original Halo CE maps
                  <span className="text-text-muted"> — and growing.</span>
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
          </Reveal>

          <ClassicMapsGrid maps={rosterMaps} />
        </section>

        {/* ── 04 / Creator Framework & Forge Pipeline ───────────────── */}
        <section className="border-y border-border bg-surface px-6 py-20 md:py-28">
          <div className="mx-auto grid max-w-6xl items-center gap-12 lg:grid-cols-2 lg:gap-16">
            <Reveal>
              <div className="mj-hud-corners relative rounded-xl border border-border-bright bg-background p-3 shadow-[0_24px_56px_-28px_rgba(0,0,0,0.9)]">
                <div className="overflow-hidden rounded-lg">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src="/blog-images/forge-building/foundry.webp"
                    alt="Foundry Forge Pack modular building pieces authored for Halo Campaign Evolved"
                    loading="lazy"
                    width={1200}
                    height={1100}
                    className="aspect-[4/3] w-full object-cover object-top transition-transform duration-700 hover:scale-[1.03]"
                  />
                </div>
                <div className="flex items-center justify-between gap-3 px-2 pb-1.5 pt-4 text-xs text-text-muted">
                  <span className="inline-flex items-center gap-2 font-medium text-foreground">
                    <Hammer aria-hidden="true" className="size-4 text-gold" /> Forge &amp; Level Pipeline
                  </span>
                  <Link href="/forge" className="font-mono text-[10px] uppercase tracking-[0.16em] text-gold hover:underline">
                    Explore Forge packs →
                  </Link>
                </div>
              </div>
            </Reveal>

            <Reveal delay={70}>
              <div>
                <p className="marketing-eyebrow">04 / A framework to build on</p>
                <h2 className="mt-4 text-3xl font-black tracking-tight md:text-4xl">
                  Make custom maps and content.
                </h2>
                <p className="mt-5 leading-7 text-text-muted">
                  Use the Blender addon, custom level pipeline, Forge packs, tag editor, and CLI to
                  build your own worlds and change the way they play. Start with a weapon or texture
                  edit, then work toward a map of your own.
                </p>

                <div className="mt-7 space-y-3">
                  {CREATOR_GUIDES.map(({ icon: Icon, ...item }) => (
                    <SpotlightCard
                      key={item.href}
                      className="rounded-xl border border-border bg-background/60 transition-colors hover:border-gold/45"
                    >
                      <Link href={item.href} className="group relative z-[2] flex items-start gap-3.5 p-4">
                        <span className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg border border-gold/25 bg-gold/10 text-gold">
                          <Icon aria-hidden="true" className="size-4" />
                        </span>
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <h3 className="text-sm font-semibold text-foreground transition-colors group-hover:text-gold">
                              {item.title}
                            </h3>
                            <span className="rounded border border-border bg-surface-raised px-1.5 py-0.5 font-mono text-[10px] text-gold">
                              {item.badge}
                            </span>
                          </div>
                          <p className="mt-1 text-xs leading-5 text-text-muted">{item.description}</p>
                        </div>
                        <ArrowRight
                          aria-hidden="true"
                          className="mt-1 size-4 shrink-0 text-text-dim transition-transform group-hover:translate-x-0.5 group-hover:text-gold"
                        />
                      </Link>
                    </SpotlightCard>
                  ))}
                </div>
              </div>
            </Reveal>
          </div>
        </section>

        {/* ── 05 / FAQ ──────────────────────────────────────────────── */}
        <section id="faq" className="mx-auto max-w-4xl scroll-mt-32 px-6 py-20 md:py-24">
          <Reveal>
            <p className="marketing-eyebrow">05 / Before your first match</p>
            <h2 className="mb-9 mt-4 text-3xl font-black tracking-tight md:text-4xl">
              Campaign Evolved multiplayer FAQ
            </h2>
            <MultiplayerFaq />
          </Reveal>
        </section>

        <CommunityCallout />
      </main>
      <Footer />
    </div>
  );
}
