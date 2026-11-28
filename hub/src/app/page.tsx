import Link from "next/link";
import {
  ArrowRight,
  Blocks,
  Box,
  Download,
  Flame,
  Hammer,
  Layers3,
  Newspaper,
  Package,
  Radio,
  Swords,
  Trophy,
} from "lucide-react";

import { Navbar } from "./components/Navbar";
import { Footer } from "./components/Footer";
import { DiscordIcon } from "./components/icons";
import { CommunityCallout, MultiplayerFaq, PlaySteps } from "./components/MultiplayerMarketing";
import { CountUp, Reveal, SpotlightCard } from "./components/Motion";
import { HeroRotator } from "./components/HeroRotator";
import { MapShowcase, type FeaturedMapItem } from "./components/MapShowcase";
import { ModesShowcase } from "./components/ModesShowcase";
import { LobbyCard } from "./components/LobbyCard";
import { ModCard } from "./components/HubKit";
import { MatchCard } from "./matches/_components/MatchCard";
import { kd } from "./matches/_components/format";
import { PlayerAvatar } from "./components/ui";
import { recordDisplay } from "./players/_components/font";
import { MiniRing } from "./players/_components/MiniRing";
import { formatPostDate } from "@/lib/blog";
import { getLandingData } from "@/lib/landing-data";
import {
  CLASSIC_MAPS,
  DISCORD_URL,
  HERO_SCENES,
  MARKETING_DESCRIPTION,
  MULTIPLAYER_IMAGES,
  MULTIPLAYER_PATH,
  marketingMetadata,
} from "@/lib/marketing";
import { TOOLS, getToolVersion } from "@/lib/tools";
import { GAME_TYPE_NAMES, MAP_GAME_NAMES, MAP_SIZES, type MapListing } from "@/kit/types";

export const metadata = marketingMetadata(
  "MJOLNIR Core — Multiplayer Modding for Halo Campaign Evolved",
  MARKETING_DESCRIPTION,
  "",
);

// Pulls live lobbies, recent matches, latest mods and map totals from D1.
export const dynamic = "force-dynamic";

const EDITORIAL_MAPS = [
  {
    code: "BGL",
    name: "Blood Gulch",
    slug: "ce-blood-gulch",
    image: MULTIPLAYER_IMAGES.bloodGulch,
    tagline: "The canyon. The bases. The memories.",
    number: "01",
    gameLabel: "Halo CE Classic",
    defaultModes: ["Slayer", "Capture the Flag"],
  },
  {
    code: "DCN",
    name: "Danger Canyon",
    slug: "ce-danger-canyon",
    image: MULTIPLAYER_IMAGES.dangerCanyon,
    tagline: "Long sightlines. Very short truces.",
    number: "02",
    gameLabel: "Halo PC Classic",
    defaultModes: ["Slayer", "Capture the Flag"],
  },
  {
    code: "CHL",
    name: "Chill Out",
    slug: "ce-chill-out",
    image: MULTIPLAYER_IMAGES.chillOut,
    tagline: "Close quarters. Keep moving.",
    number: "03",
    gameLabel: "Halo CE Classic",
    defaultModes: ["Slayer", "Oddball", "King of the Hill"],
  },
];

function buildShowcaseMaps(liveMaps: MapListing[]): FeaturedMapItem[] {
  const bySlug = new Map(liveMaps.map((m) => [m.slug, m]));
  const items: FeaturedMapItem[] = EDITORIAL_MAPS.map((ed) => {
    const live = bySlug.get(ed.slug);
    const playersLabel =
      live && live.players_min !== null && live.players_max !== null
        ? `${live.players_min}–${live.players_max} players`
        : "2–16 players";
    return {
      code: live?.code ?? ed.code,
      name: live?.title ?? ed.name,
      slug: ed.slug,
      image: live?.cover_url ?? ed.image,
      tagline: ed.tagline,
      number: ed.number,
      gameLabel: live?.game ? MAP_GAME_NAMES[live.game] : ed.gameLabel,
      modes: live && live.modes.length > 0 ? live.modes.map((m) => GAME_TYPE_NAMES[m] ?? m) : ed.defaultModes,
      playersLabel,
      sizeLabel: live?.size ? MAP_SIZES[live.size] : null,
      vehicles: live?.vehicles ?? (ed.code !== "CHL"),
      downloads: live?.download_count ?? null,
      hasRelease: Boolean(live?.release),
    };
  });

  // Add up to 2 extra high-profile maps from D1 (e.g. a Halo 2 classic or popular community map)
  const usedSlugs = new Set(items.map((i) => i.slug));
  const extras = liveMaps
    .filter((m) => !usedSlugs.has(m.slug) && m.cover_url)
    .sort((a, b) => {
      // Surface a Halo 2 map first if present, then most downloaded
      const aH2 = a.game === "halo2" ? 1 : 0;
      const bH2 = b.game === "halo2" ? 1 : 0;
      return bH2 - aH2 || b.download_count - a.download_count;
    })
    .slice(0, 2);

  extras.forEach((m, idx) => {
    const num = String(items.length + 1).padStart(2, "0");
    items.push({
      code: m.code,
      name: m.title,
      slug: m.slug,
      image: m.cover_url!,
      tagline: m.summary ?? (m.official ? "Rebuilt classic arena ready for 16-player combat." : `Community arena by ${m.owner}.`),
      number: num,
      gameLabel: m.game ? MAP_GAME_NAMES[m.game] : m.official ? "Classic" : "Community",
      modes: m.modes.length > 0 ? m.modes.map((mode) => GAME_TYPE_NAMES[mode] ?? mode) : ["Slayer"],
      playersLabel:
        m.players_min !== null && m.players_max !== null
          ? `${m.players_min}–${m.players_max} players`
          : null,
      sizeLabel: m.size ? MAP_SIZES[m.size] : null,
      vehicles: m.vehicles,
      downloads: m.download_count,
      hasRelease: Boolean(m.release),
    });
    void idx;
  });

  return items;
}

const PLACE_COLOR = { 1: "text-gold", 2: "text-silver", 3: "text-bronze" } as const;

export default async function HomePage() {
  const data = await getLandingData();
  const showcaseMaps = buildShowcaseMaps(data.maps);
  const mapTotal = Math.max(data.totals.maps, CLASSIC_MAPS.length);
  const hasHubPulse =
    data.lobbies.length > 0 ||
    data.recentMatches.length > 0 ||
    data.latestMods.length > 0 ||
    data.topPlayers.length > 0;

  // Prefer live cover URLs from D1 when available, falling back to published media captures.
  const coversBySlug = new Map(data.maps.map((m) => [m.slug, m.cover_url]));
  const heroScenes = HERO_SCENES.map((scene) => ({
    ...scene,
    image: coversBySlug.get(scene.slug) ?? scene.image,
  }));

  const tagEditor = TOOLS.find((t) => t.slug === "tag-editor");
  const cliTool = TOOLS.find((t) => t.slug === "cli");
  const tagEditorVersion = tagEditor ? getToolVersion(tagEditor) : null;
  const cliVersion = cliTool ? getToolVersion(cliTool) : null;

  return (
    <div className={recordDisplay.variable}>
      <Navbar />
      <main id="main" className="marketing">
        {/* ── 00 / Cinematic Hero with Rotating Map Vistas ───────────── */}
        <HeroRotator scenes={heroScenes} multiplayerHref={MULTIPLAYER_PATH}>
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
                  {data.livePlayers} Spartan{data.livePlayers === 1 ? "" : "s"} online
                </Link>
              ) : (
                <Link
                  href={data.totals.matches > 0 ? "/matches" : MULTIPLAYER_PATH}
                  className="inline-flex items-center gap-2.5 rounded-full border border-gold/30 bg-background/65 px-3.5 py-1.5 font-mono text-[11px] font-medium uppercase tracking-[0.18em] text-gold backdrop-blur-md transition-colors hover:border-gold/60"
                >
                  <span className="relative flex size-2 items-center justify-center" aria-hidden="true">
                    <span className="mj-live-ring absolute inline-flex size-full rounded-full bg-gold/70" />
                    <span className="relative inline-flex size-1.5 rounded-full bg-gold" />
                  </span>
                  Multiplayer alpha is live
                  {data.totals.matches > 0 && (
                    <span className="text-slate-300">
                      · {data.totals.matches.toLocaleString("en-US")} matches logged
                    </span>
                  )}
                </Link>
              )}
            </div>

            <h1 className="mj-rise mj-rise-d1 mt-6 text-[42px] font-black leading-[1.01] tracking-[-0.05em] sm:text-6xl lg:text-[74px]">
              The multiplayer
              <br />
              modding framework
              <br />
              <span className="bg-gradient-to-r from-[#f0ca69] via-gold to-[#c49230] bg-clip-text text-transparent">
                for Campaign Evolved.
              </span>
            </h1>

            <p className="mj-rise mj-rise-d2 mt-6 max-w-xl text-base leading-7 text-slate-200 md:text-lg md:leading-8">
              Classic Halo multiplayer, back in your hands. Play Slayer, CTF, and Forge on the
              original Halo: CE &amp; Halo 2 maps. Build custom worlds. Bring your fireteam.
            </p>

            <div className="mj-rise mj-rise-d3 mt-8 flex flex-col gap-3 sm:flex-row">
              <Link href="/download" className="marketing-button-primary">
                <Download aria-hidden="true" className="size-4" /> Get MJOLNIR{" "}
                <ArrowRight aria-hidden="true" className="size-4" />
              </Link>
              <Link href={DISCORD_URL} className="marketing-button-secondary">
                <DiscordIcon className="size-5" /> Join the community
              </Link>
            </div>

            <p className="mj-rise mj-rise-d4 mt-5 text-xs leading-6 text-slate-300">
              Free &amp; open source · Windows PC · Steam &amp; Game Pass crossplay
            </p>
          </div>
        </HeroRotator>

        {/* ── Kinetic Live Telemetry Strip ───────────────────────────── */}
        <div className="border-y border-border bg-surface">
          <div className="mx-auto grid max-w-6xl grid-cols-2 px-6 md:grid-cols-4">
            <Link
              href="/maps"
              className="group border-b border-border py-6 pr-4 transition-colors hover:bg-surface-raised/60 md:border-b-0 md:py-7 md:pr-6"
            >
              <p className="record-display text-4xl leading-none text-foreground transition-colors group-hover:text-gold sm:text-5xl">
                <CountUp value={mapTotal} />
              </p>
              <p className="mt-2 font-mono text-[10px] uppercase tracking-[0.16em] text-text-muted">
                Multiplayer maps
              </p>
            </Link>

            <Link
              href="/matches"
              className="group border-b border-l border-border py-6 pl-5 transition-colors hover:bg-surface-raised/60 md:border-b-0 md:py-7 md:pl-6"
            >
              <p className="record-display text-4xl leading-none text-foreground transition-colors group-hover:text-gold sm:text-5xl">
                {data.totals.matches > 0 ? <CountUp value={data.totals.matches} /> : "16P"}
              </p>
              <p className="mt-2 font-mono text-[10px] uppercase tracking-[0.16em] text-text-muted">
                {data.totals.matches > 0 ? "Public matches logged" : "Max fireteam size"}
              </p>
            </Link>

            <Link
              href="/mods"
              className="group py-6 pr-4 transition-colors hover:bg-surface-raised/60 md:border-l md:border-border md:py-7 md:pl-6 md:pr-6"
            >
              <p className="record-display text-4xl leading-none text-foreground transition-colors group-hover:text-gold sm:text-5xl">
                {data.totals.mods > 0 ? <CountUp value={data.totals.mods} /> : "OSS"}
              </p>
              <p className="mt-2 font-mono text-[10px] uppercase tracking-[0.16em] text-text-muted">
                {data.totals.mods > 0 ? "Community mods & packs" : "Free & open source"}
              </p>
            </Link>

            <Link
              href={data.livePlayers > 0 ? "/games" : data.totals.kills > 0 ? "/leaderboards" : "/games"}
              className="group border-l border-border py-6 pl-5 transition-colors hover:bg-surface-raised/60 md:py-7 md:pl-6"
            >
              <p
                className={`record-display text-4xl leading-none transition-colors sm:text-5xl ${
                  data.livePlayers > 0 ? "text-accent-green" : "text-gold"
                }`}
              >
                {data.livePlayers > 0 ? (
                  <CountUp value={data.livePlayers} />
                ) : data.totals.kills > 0 ? (
                  <CountUp value={data.totals.kills} />
                ) : (
                  "LIVE"
                )}
              </p>
              <p className="mt-2 font-mono text-[10px] uppercase tracking-[0.16em] text-text-muted">
                {data.livePlayers > 0
                  ? `Playing across ${data.lobbies.length} live game${data.lobbies.length === 1 ? "" : "s"}`
                  : data.totals.kills > 0
                    ? "Total kills recorded"
                    : "Public lobby browser"}
              </p>
            </Link>
          </div>
        </div>

        {/* ── 01 / Interactive Battleground Showcase ─────────────────── */}
        <section className="mx-auto max-w-6xl px-6 py-20 md:py-28">
          <Reveal>
            <div className="flex flex-col justify-between gap-6 md:flex-row md:items-end">
              <div>
                <p className="marketing-eyebrow">01 / Familiar ground</p>
                <h2 className="mt-4 text-4xl font-black tracking-tight md:text-5xl">
                  Same maps.
                  <br />
                  <span className="text-text-muted">New possibilities.</span>
                </h2>
              </div>
              <div className="max-w-md">
                <p className="leading-7 text-text-muted">
                  From Blood Gulch to Hang &apos;Em High. All 19 original Halo: Combat Evolved
                  multiplayer maps, Halo 2 classics, and custom community arenas rebuilt for Campaign Evolved.
                </p>
                <Link href="/maps" className="mt-5 inline-flex items-center gap-2 text-sm font-semibold text-gold hover:underline">
                  Explore all {mapTotal} maps <ArrowRight aria-hidden="true" className="size-4" />
                </Link>
              </div>
            </div>
          </Reveal>

          <Reveal delay={80}>
            <MapShowcase maps={showcaseMaps} />
          </Reveal>
        </section>

        {/* ── 02 / Live on the Hub: Lobbies, Recent Matches, Mods & Podium */}
        <section className="relative border-y border-border bg-surface px-6 py-20 md:py-28">
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-gold/40 to-transparent"
          />
          <div className="mx-auto max-w-6xl space-y-14">
            <Reveal>
              <div className="flex flex-col justify-between gap-6 md:flex-row md:items-end">
                <div>
                  <p className="marketing-eyebrow">02 / Live on the hub</p>
                  <h2 className="mt-4 text-4xl font-black tracking-tight md:text-5xl">
                    Recent battles.
                    <br />
                    <span className="text-gold">Fresh workshop drops.</span>
                  </h2>
                </div>
                <p className="max-w-md leading-7 text-text-muted">
                  Every public match reports its scoreboard, podium, and 3D kill positions right back
                  to the hub — alongside live lobbies, leaderboards, and the latest community mods.
                </p>
              </div>
            </Reveal>

            {hasHubPulse ? (
              <>
                {/* Live Games Strip (shown whenever lobbies are open) */}
                {data.lobbies.length > 0 && (
                  <Reveal>
                    <div className="mb-4 flex items-center justify-between gap-4">
                      <h3 className="inline-flex items-center gap-2 font-mono text-xs font-semibold uppercase tracking-[0.16em] text-accent-green">
                        <Radio aria-hidden="true" className="size-4" />
                        Live multiplayer lobbies ({data.lobbies.length})
                      </h3>
                      <Link href="/games" className="inline-flex items-center gap-1.5 text-sm font-semibold text-gold hover:underline">
                        View all live games <ArrowRight aria-hidden="true" className="size-4" />
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

                {/* Recent Public Matches */}
                {data.recentMatches.length > 0 && (
                  <Reveal delay={60}>
                    <div className="mb-5 flex flex-wrap items-center justify-between gap-4">
                      <h3 className="inline-flex items-center gap-2 font-mono text-xs font-semibold uppercase tracking-[0.16em] text-text-muted">
                        <Swords aria-hidden="true" className="size-4 text-gold" />
                        Recent public matches
                      </h3>
                      <Link href="/matches" className="inline-flex items-center gap-1.5 text-sm font-semibold text-gold hover:underline">
                        Full match history &amp; 3D kill maps <ArrowRight aria-hidden="true" className="size-4" />
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

                {/* Top Spartans Career Ring Podium */}
                {data.topPlayers.length > 0 && (
                  <Reveal delay={80}>
                    <div className="relative overflow-hidden rounded-2xl border border-border-bright bg-background/75 p-6 sm:p-8">
                      <div aria-hidden="true" className="record-ripple opacity-45" />
                      <div className="relative flex flex-wrap items-end justify-between gap-4 mb-6">
                        <div>
                          <p className="inline-flex items-center gap-2 font-mono text-[11px] font-semibold uppercase tracking-[0.18em] text-gold">
                            <Trophy aria-hidden="true" className="size-3.5" />
                            Combat record leaders
                          </p>
                          <h3 className="mt-1.5 text-2xl font-black tracking-tight text-foreground">
                            Top Spartans on the boards
                          </h3>
                        </div>
                        <Link href="/leaderboards" className="inline-flex items-center gap-1.5 text-sm font-semibold text-gold hover:underline">
                          Explore all leaderboards <ArrowRight aria-hidden="true" className="size-4" />
                        </Link>
                      </div>
                      <ol className="relative grid gap-5 sm:grid-cols-3">
                        {data.topPlayers.map((standing) => (
                          <li key={standing.user.id}>
                            <Link
                              href={`/users/${standing.user.id}`}
                              className="group flex items-center gap-4 rounded-xl border border-border bg-surface/90 p-4 transition-all duration-200 hover:-translate-y-0.5 hover:border-gold/50"
                            >
                              <div className="w-20 shrink-0">
                                <MiniRing
                                  matches={data.topRings[standing.user.id] ?? []}
                                  center={<PlayerAvatar name={standing.user.name} user={standing.user} size="md" />}
                                />
                              </div>
                              <div className="min-w-0 flex-1">
                                <div className="flex items-baseline gap-2">
                                  <span
                                    className={`record-display text-2xl leading-none ${
                                      PLACE_COLOR[standing.rank as 1 | 2 | 3] ?? "text-text-muted"
                                    }`}
                                  >
                                    #{standing.rank}
                                  </span>
                                  <span className="truncate font-bold text-foreground transition-colors group-hover:text-gold">
                                    {standing.user.name}
                                  </span>
                                </div>
                                <p className="record-display mt-1 text-3xl leading-none text-foreground tabular-nums">
                                  {standing.value.toLocaleString("en-US")}{" "}
                                  <span className="font-sans text-xs font-normal text-text-muted">kills</span>
                                </p>
                                <p className="mt-1 text-xs text-text-dim tabular-nums">
                                  {kd(standing.kills, standing.deaths)} K/D · {standing.matches} matches
                                </p>
                              </div>
                            </Link>
                          </li>
                        ))}
                      </ol>
                    </div>
                  </Reveal>
                )}

                {/* Latest Community Mods */}
                {data.latestMods.length > 0 && (
                  <Reveal delay={100}>
                    <div className="mb-5 flex flex-wrap items-center justify-between gap-4">
                      <h3 className="inline-flex items-center gap-2 font-mono text-xs font-semibold uppercase tracking-[0.16em] text-text-muted">
                        <Flame aria-hidden="true" className="size-4 text-gold" />
                        Latest community mods
                      </h3>
                      <div className="flex items-center gap-5 text-sm font-semibold">
                        <Link href="/forge" className="inline-flex items-center gap-1.5 text-text-muted hover:text-foreground">
                          <Blocks aria-hidden="true" className="size-4 text-gold" />
                          Forge packs
                        </Link>
                        <Link href="/mods" className="inline-flex items-center gap-1.5 text-gold hover:underline">
                          Browse all mods <ArrowRight aria-hidden="true" className="size-4" />
                        </Link>
                      </div>
                    </div>
                    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                      {data.latestMods.map((mod) => (
                        <ModCard key={mod.id} mod={mod} href={`/mods/${mod.slug}`} />
                      ))}
                    </div>
                  </Reveal>
                )}
              </>
            ) : (
              /* Clean fallback grid if local D1 has no seeded rows yet */
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                {[
                  {
                    icon: Radio,
                    title: "Live Games",
                    body: "Browse open public lobbies with estimated ping and 1-click launcher joins.",
                    href: "/games",
                    cta: "Open game browser",
                  },
                  {
                    icon: Swords,
                    title: "Match History",
                    body: "Full scoreboards, Red vs. Blue summaries, and interactive 3D kill maps.",
                    href: "/matches",
                    cta: "Inspect matches",
                  },
                  {
                    icon: Package,
                    title: "Community Mods",
                    body: "Scanned texture swaps, weapon tunings, Forge packs, and signed script mods.",
                    href: "/mods",
                    cta: "Browse workshop",
                  },
                  {
                    icon: Trophy,
                    title: "Leaderboards",
                    body: "Career combat rings, K/D rankings, wins, headshots, and best matches.",
                    href: "/leaderboards",
                    cta: "View standings",
                  },
                ].map(({ icon: Icon, ...card }, idx) => (
                  <Reveal key={card.title} delay={idx * 70}>
                    <SpotlightCard className="h-full rounded-xl border border-border-bright bg-background/65 p-5">
                      <Link href={card.href} className="group relative z-[2] flex h-full flex-col">
                        <span className="inline-flex size-10 items-center justify-center rounded-lg border border-gold/30 bg-gold/10 text-gold">
                          <Icon aria-hidden="true" className="size-5" />
                        </span>
                        <h3 className="mt-4 text-lg font-bold text-foreground transition-colors group-hover:text-gold">
                          {card.title}
                        </h3>
                        <p className="mt-2 flex-1 text-sm leading-6 text-text-muted">{card.body}</p>
                        <span className="mt-4 inline-flex items-center gap-1.5 text-xs font-semibold text-gold">
                          {card.cta} <ArrowRight aria-hidden="true" className="size-3.5 transition-transform group-hover:translate-x-0.5" />
                        </span>
                      </Link>
                    </SpotlightCard>
                  </Reveal>
                ))}
              </div>
            )}
          </div>
        </section>

        {/* ── 03 / Pick your game — Interactive Modes Showcase ───────── */}
        <section className="mx-auto max-w-6xl px-6 py-20 md:py-28">
          <Reveal>
            <p className="marketing-eyebrow">03 / Pick your game</p>
            <div className="mt-4 grid gap-10 lg:grid-cols-[0.82fr_1.18fr] lg:gap-16">
              <div>
                <h2 className="text-4xl font-black leading-tight tracking-tight md:text-5xl">
                  One more match.
                  <br />
                  <span className="text-gold">You know the feeling.</span>
                </h2>
                <p className="mt-6 leading-7 text-text-muted">
                  The chase for the last kill. A flag run that should never have worked. MJOLNIR
                  brings classic competitive multiplayer to Halo Campaign Evolved, with its own
                  lobby, a browser for public games, match chat, a scoreboard, Forge, and a
                  team-aware multiplayer HUD.
                </p>
                <div className="mt-6 flex flex-wrap gap-5 text-sm font-semibold">
                  <Link href={MULTIPLAYER_PATH} className="inline-flex items-center gap-2 text-gold hover:underline">
                    Discover Campaign Evolved multiplayer <ArrowRight aria-hidden="true" className="size-4" />
                  </Link>
                  <Link href="/games" className="inline-flex items-center gap-2 text-text-muted hover:text-foreground">
                    Live games <ArrowRight aria-hidden="true" className="size-4" />
                  </Link>
                </div>
              </div>

              <ModesShowcase />
            </div>
          </Reveal>
        </section>

        {/* ── 04 / Make it yours — Creator Tools & Latest Dispatch ───── */}
        <section className="border-y border-border bg-surface px-6 py-20 md:py-28">
          <div className="mx-auto max-w-6xl">
            <div className="grid items-center gap-12 lg:grid-cols-2 lg:gap-16">
              <Reveal>
                <div className="mj-hud-corners relative rounded-xl border border-border-bright bg-background p-3 shadow-[0_24px_56px_-28px_rgba(0,0,0,0.9)]">
                  <div className="overflow-hidden rounded-lg">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src="/docs-images/texture_swap_assault_rifle.jpg"
                      alt="A custom red assault rifle texture made with MJOLNIR in Halo Campaign Evolved"
                      loading="lazy"
                      width={1280}
                      height={720}
                      className="aspect-[4/3] w-full object-cover transition-transform duration-700 hover:scale-[1.03]"
                    />
                  </div>
                  <div className="flex items-center justify-between gap-3 px-2 pb-1.5 pt-4 text-xs text-text-muted">
                    <span className="inline-flex items-center gap-2 font-medium text-foreground">
                      <Hammer aria-hidden="true" className="size-4 text-gold" /> Made with MJOLNIR
                    </span>
                    <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-gold">
                      Your content. In game.
                    </span>
                  </div>
                </div>
              </Reveal>

              <Reveal delay={90}>
                <div>
                  <p className="marketing-eyebrow">04 / Make it yours</p>
                  <h2 className="mt-4 text-4xl font-black tracking-tight md:text-5xl">
                    The next great map
                    <br />
                    could be yours.
                  </h2>
                  <p className="mt-6 leading-7 text-text-muted">
                    MJOLNIR is an open multiplayer modding framework for players and creators. Build
                    custom levels, craft Forge packs, rework weapons, swap textures, and write scripts.
                    Then publish straight to the hub.
                  </p>

                  <div className="mt-7 space-y-3">
                    {[
                      {
                        icon: Box,
                        title: "Build custom maps",
                        badge: "Blender + Level Pipeline",
                        text: "Author arenas in Blender, cook into native containers, and publish directly to /maps.",
                        href: "/docs/guides/level-authoring",
                      },
                      {
                        icon: Layers3,
                        title: "Edit tags, textures & audio",
                        badge: tagEditorVersion ? `Tag Editor v${tagEditorVersion}` : "Tag Editor",
                        text: "Inspect and tweak cooked game assets with the standalone MJOLNIR Tag Editor.",
                        href: "/tools/tag-editor",
                      },
                      {
                        icon: Hammer,
                        title: "Package & ship from the CLI",
                        badge: cliVersion ? `mjolnir v${cliVersion}` : "CLI",
                        text: "Script tag edits, pack Forge kits, and publish signed releases from Windows, macOS, or Linux.",
                        href: "/tools/cli",
                      },
                    ].map(({ icon: Icon, ...item }) => (
                      <SpotlightCard
                        key={item.title}
                        className="rounded-xl border border-border bg-background/60 transition-colors hover:border-gold/45"
                      >
                        <Link href={item.href} className="group relative z-[2] flex items-start gap-4 p-4">
                          <span className="mt-0.5 flex size-9 shrink-0 items-center justify-center rounded-lg border border-gold/25 bg-gold/10 text-gold">
                            <Icon aria-hidden="true" className="size-4" />
                          </span>
                          <div className="min-w-0 flex-1">
                            <div className="flex flex-wrap items-center gap-2">
                              <h3 className="font-semibold text-foreground transition-colors group-hover:text-gold">
                                {item.title}
                              </h3>
                              <span className="rounded bg-surface-raised px-1.5 py-0.5 font-mono text-[10px] text-gold border border-border">
                                {item.badge}
                              </span>
                            </div>
                            <p className="mt-1 text-sm leading-6 text-text-muted">{item.text}</p>
                          </div>
                          <ArrowRight
                            aria-hidden="true"
                            className="mt-1 size-4 shrink-0 text-text-dim transition-transform group-hover:translate-x-0.5 group-hover:text-gold"
                          />
                        </Link>
                      </SpotlightCard>
                    ))}
                  </div>

                  <div className="mt-7 flex flex-wrap items-center gap-6 text-sm font-semibold">
                    <Link href="/tools" className="inline-flex items-center gap-2 text-gold hover:underline">
                      Explore creator tools <ArrowRight aria-hidden="true" className="size-4" />
                    </Link>
                    <Link href="/docs" className="inline-flex items-center gap-2 text-text-muted hover:text-foreground">
                      Read the docs <ArrowRight aria-hidden="true" className="size-4" />
                    </Link>
                  </div>
                </div>
              </Reveal>
            </div>

            {/* Latest Engineering Dispatch from /blog */}
            {data.latestPost && (
              <Reveal delay={120} className="mt-14">
                <Link
                  href={`/blog/${data.latestPost.slug}`}
                  className="group flex flex-col justify-between gap-5 rounded-xl border border-border-bright bg-background/70 p-6 transition-all duration-200 hover:-translate-y-0.5 hover:border-gold/50 md:flex-row md:items-center"
                >
                  <div className="flex items-start gap-4 min-w-0">
                    <span className="flex size-11 shrink-0 items-center justify-center rounded-xl border border-gold/30 bg-gold/10 text-gold">
                      <Newspaper aria-hidden="true" className="size-5" />
                    </span>
                    <div className="min-w-0">
                      <p className="font-mono text-[10px] font-semibold uppercase tracking-[0.18em] text-gold">
                        Latest dispatch · {formatPostDate(data.latestPost.date)}
                      </p>
                      <h3 className="mt-1 text-lg font-bold text-foreground transition-colors group-hover:text-gold">
                        {data.latestPost.title}
                      </h3>
                      <p className="mt-1 line-clamp-2 max-w-2xl text-sm text-text-muted">
                        {data.latestPost.summary}
                      </p>
                    </div>
                  </div>
                  <span className="inline-flex shrink-0 items-center gap-1.5 text-sm font-semibold text-gold">
                    Read post <ArrowRight aria-hidden="true" className="size-4 transition-transform group-hover:translate-x-1" />
                  </span>
                </Link>
              </Reveal>
            )}
          </div>
        </section>

        {/* ── 05 / See you on the map — Connected 3-Step Drop-In ─────── */}
        <section className="mx-auto max-w-6xl px-6 py-20 md:py-24">
          <Reveal>
            <div className="mb-10 flex flex-wrap items-end justify-between gap-6">
              <div>
                <p className="marketing-eyebrow">05 / See you on the map</p>
                <h2 className="mt-4 text-4xl font-black tracking-tight">Three steps to your first match.</h2>
              </div>
              <Link href="/download" className="marketing-button-primary">
                Get the launcher <Download aria-hidden="true" className="size-4" />
              </Link>
            </div>
          </Reveal>
          <PlaySteps />
        </section>

        {/* ── FAQ ────────────────────────────────────────────────────── */}
        <section className="border-t border-border bg-surface/40 px-6 py-20 md:py-24">
          <div className="mx-auto max-w-4xl">
            <Reveal>
              <p className="marketing-eyebrow">A few things before you drop in</p>
              <h2 className="mb-9 mt-4 text-3xl font-black tracking-tight md:text-4xl">
                Campaign Evolved multiplayer, explained.
              </h2>
              <MultiplayerFaq compact />
              <Link
                href={MULTIPLAYER_PATH + "#faq"}
                className="mt-7 inline-flex items-center gap-2 text-sm font-semibold text-gold hover:underline"
              >
                All multiplayer FAQs &amp; setup details <ArrowRight aria-hidden="true" className="size-4" />
              </Link>
            </Reveal>
          </div>
        </section>

        <CommunityCallout />
      </main>
      <Footer />
    </div>
  );
}
