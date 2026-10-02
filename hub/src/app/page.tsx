import Link from "next/link";
import { ArrowRight, Box, Crosshair, Download, Flag, Hammer, Layers3 } from "lucide-react";
import { Navbar } from "./components/Navbar";
import { Footer } from "./components/Footer";
import { DiscordIcon } from "./components/icons";
import { CommunityCallout, MultiplayerFaq, PlaySteps } from "./components/MultiplayerMarketing";
import {
  CLASSIC_MAPS,
  DISCORD_URL,
  MARKETING_DESCRIPTION,
  MULTIPLAYER_IMAGES,
  MULTIPLAYER_PATH,
  marketingMetadata,
} from "@/lib/marketing";

export const metadata = marketingMetadata(
  "MJOLNIR Core — Multiplayer Modding for Halo Campaign Evolved",
  MARKETING_DESCRIPTION,
  "",
);

const featuredMaps = [
  { name: "Blood Gulch", slug: "ce-blood-gulch", image: MULTIPLAYER_IMAGES.bloodGulch, label: "The canyon. The bases. The memories.", number: "01" },
  { name: "Danger Canyon", slug: "ce-danger-canyon", image: MULTIPLAYER_IMAGES.dangerCanyon, label: "Long sightlines. Very short truces.", number: "02" },
  { name: "Chill Out", slug: "ce-chill-out", image: MULTIPLAYER_IMAGES.chillOut, label: "Close quarters. Keep moving.", number: "03" },
];

export default function HomePage() {
  return (
    <>
      <Navbar />
      <main className="marketing">
        <section className="marketing-hero relative isolate overflow-hidden">
          {/* Published gameplay capture, served unchanged by the hub's media API. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={MULTIPLAYER_IMAGES.bloodGulch} alt="The classic Blood Gulch canyon and bases rebuilt inside Halo Campaign Evolved" fetchPriority="high" className="marketing-hero-image absolute inset-0 -z-20 size-full object-cover" />
          <div className="marketing-hero-shade absolute inset-0 -z-10" />
          <div className="mx-auto max-w-6xl px-6 pb-12 pt-44 md:pb-16 md:pt-52">
            <div className="flex items-center gap-3 font-mono text-[11px] font-medium uppercase tracking-[0.2em] text-gold">
              <span className="size-1.5 bg-gold" /> Multiplayer alpha is here
            </div>
            <h1 className="mt-7 max-w-4xl text-[40px] font-black leading-[1.02] tracking-[-0.055em] sm:text-6xl lg:text-[72px]">
              The multiplayer<br />modding framework<br />
              <span className="text-gold">for Campaign Evolved.</span>
            </h1>
            <p className="mt-7 max-w-lg text-base leading-7 text-slate-300 md:text-lg md:leading-8">
              Classic Halo multiplayer, back in your hands. Play Slayer and CTF on all {CLASSIC_MAPS.length} original Halo: CE maps. Build custom maps and content. Bring your friends.
            </p>
            <div className="mt-9 flex flex-col gap-3 sm:flex-row">
              <Link href="/download" className="marketing-button-primary"><Download aria-hidden="true" className="size-4" /> Get MJOLNIR <ArrowRight aria-hidden="true" className="size-4" /></Link>
              <Link href={DISCORD_URL} className="marketing-button-secondary"><DiscordIcon className="size-5" /> Join the community</Link>
            </div>
            <p className="mt-5 text-xs leading-6 text-slate-300">Free &amp; open source · Windows PC · Requires Halo Campaign Evolved</p>
            <div className="mt-16 flex flex-wrap items-end justify-between gap-5 border-t border-white/15 pt-6">
              <Link href={MULTIPLAYER_PATH} className="inline-flex items-center gap-3 text-sm font-semibold text-white hover:text-gold">Does Campaign Evolved have multiplayer? <ArrowRight aria-hidden="true" className="size-4" /></Link>
              <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-slate-300">In-game capture / Blood Gulch</span>
            </div>
          </div>
        </section>

        <div className="border-y border-border bg-surface">
          <div className="mx-auto grid max-w-6xl grid-cols-2 px-6 md:grid-cols-4">
            {[
              { value: "19", label: "Classic Halo CE maps" },
              { value: "Slayer + CTF", label: "And more game modes" },
              { value: "Play + create", label: "Custom maps & content" },
              { value: "Open source", label: "Built with the community" },
            ].map((item) => (
              <div key={item.label} className="border-l border-border py-7 pl-5 first:border-l-0 first:pl-0 md:py-8">
                <p className="text-lg font-bold text-foreground sm:text-2xl">{item.value}</p>
                <p className="mt-2 font-mono text-[10px] uppercase tracking-wider text-text-muted">{item.label}</p>
              </div>
            ))}
          </div>
        </div>

        <section className="mx-auto max-w-6xl px-6 py-20 md:py-28">
          <div className="flex flex-col justify-between gap-6 md:flex-row md:items-end">
            <div>
              <p className="marketing-eyebrow">01 / Familiar ground</p>
              <h2 className="mt-4 text-4xl font-black tracking-tight md:text-5xl">Same maps.<br /><span className="text-text-muted">New possibilities.</span></h2>
            </div>
            <div className="max-w-md">
              <p className="leading-7 text-text-muted">From Blood Gulch to Hang &apos;Em High. All 19 original Halo: Combat Evolved multiplayer maps, including the Halo PC classics, rebuilt for Campaign Evolved.</p>
              <Link href="/maps" className="mt-5 inline-flex items-center gap-2 text-sm font-semibold text-gold hover:underline">Explore all 19 maps <ArrowRight aria-hidden="true" className="size-4" /></Link>
            </div>
          </div>
          <div className="mt-10 grid gap-5 md:grid-cols-3">
            {featuredMaps.map((map) => (
              <Link key={map.slug} href={"/mods/" + map.slug} className="group overflow-hidden border border-border bg-surface transition-colors hover:border-gold/50">
                <div className="relative overflow-hidden">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={map.image} alt={map.name + " in Halo Campaign Evolved with MJOLNIR"} loading="lazy" width={640} height={360} className="aspect-video w-full object-cover transition-transform duration-500 group-hover:scale-105" />
                  <span className="absolute left-4 top-4 bg-background/80 px-2 py-1 font-mono text-[10px] tracking-widest text-gold">CE / {map.number}</span>
                </div>
                <div className="p-5">
                  <div className="flex items-center justify-between"><h3 className="text-xl font-bold">{map.name}</h3><ArrowRight aria-hidden="true" className="size-4 text-gold" /></div>
                  <p className="mt-2 text-sm text-text-muted">{map.label}</p>
                  <p className="mt-5 font-mono text-[10px] uppercase tracking-widest text-gold">Slayer / Capture the Flag</p>
                </div>
              </Link>
            ))}
          </div>
        </section>

        <section className="border-y border-border bg-surface px-6 py-20 md:py-24">
          <div className="mx-auto max-w-6xl">
            <p className="marketing-eyebrow">02 / Pick your game</p>
            <div className="mt-4 grid gap-10 lg:grid-cols-[0.9fr_1.1fr] lg:gap-20">
              <div>
                <h2 className="text-4xl font-black leading-tight tracking-tight md:text-5xl">One more match.<br /><span className="text-gold">You know the feeling.</span></h2>
                <p className="mt-6 leading-7 text-text-muted">The chase for the last kill. A flag run that should never have worked. MJOLNIR brings classic competitive multiplayer to Halo Campaign Evolved, with its own lobby, scoreboard, and multiplayer HUD.</p>
                <Link href={MULTIPLAYER_PATH} className="mt-6 inline-flex items-center gap-2 text-sm font-semibold text-gold hover:underline">Discover Campaign Evolved multiplayer <ArrowRight aria-hidden="true" className="size-4" /></Link>
              </div>
              <div>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="border border-border-bright bg-background/50 p-6"><Crosshair aria-hidden="true" className="size-8 text-gold" /><h3 className="mt-5 text-2xl font-bold">Slayer</h3><p className="mt-3 text-sm leading-6 text-text-muted">Every kill counts. Find your weapon, learn the angles, and climb the scoreboard.</p></div>
                  <div className="border border-border-bright bg-background/50 p-6"><Flag aria-hidden="true" className="size-8 text-gold" /><h3 className="mt-5 text-2xl font-bold">Capture the Flag</h3><p className="mt-3 text-sm leading-6 text-text-muted">Defend your base. Take theirs. Get the flag home with your fireteam at your side.</p></div>
                </div>
                <p className="mt-6 text-sm font-medium">Plus framework support for</p>
                <div className="mt-3 flex flex-wrap gap-2">{["Team Slayer", "King of the Hill", "Oddball"].map((mode) => <span key={mode} className="border border-border-bright px-3 py-1.5 text-xs text-text-muted">{mode}</span>)}</div>
                <p className="mt-4 text-xs leading-6 text-text-muted">Available modes depend on the map and installed game variant. The current alpha supports up to four players.</p>
              </div>
            </div>
          </div>
        </section>

        <section className="mx-auto grid max-w-6xl items-center gap-12 px-6 py-20 md:py-28 lg:grid-cols-2 lg:gap-20">
          <div className="relative border border-border bg-surface p-3">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/docs-images/texture_swap_assault_rifle.jpg" alt="A custom red assault rifle texture made with MJOLNIR in Halo Campaign Evolved" loading="lazy" width={1280} height={720} className="aspect-[4/3] w-full object-cover" />
            <div className="flex items-center justify-between gap-3 px-2 pb-2 pt-5 text-xs text-text-muted"><span className="inline-flex items-center gap-2"><Hammer aria-hidden="true" className="size-4 text-gold" /> Made with MJOLNIR</span><span className="font-mono text-[10px] uppercase">Your content. In game.</span></div>
          </div>
          <div>
            <p className="marketing-eyebrow">03 / Make it yours</p>
            <h2 className="mt-4 text-4xl font-black tracking-tight md:text-5xl">The next great map<br />could be yours.</h2>
            <p className="mt-6 leading-7 text-text-muted">MJOLNIR is a multiplayer modding framework for players and creators. Build custom levels, rework weapons, swap textures, and write scripts. Then share what you make with the community.</p>
            <div className="mt-7 space-y-5">
              {[
                { icon: Box, title: "Build custom maps", text: "A Blender addon and level pipeline for your own battlegrounds.", href: "/docs/guides/level-authoring" },
                { icon: Layers3, title: "Create custom content", text: "Edit tags, textures, and scripts with the MJOLNIR Tag Editor.", href: "/docs/guides/making-your-first-mod" },
                { icon: Hammer, title: "Share it with the community", text: "Package your work and publish through the hub.", href: "/docs/notes/map-distribution" },
              ].map(({ icon: Icon, ...item }) => (
                <Link key={item.title} href={item.href} className="group flex items-start gap-4">
                  <Icon aria-hidden="true" className="mt-1 size-5 shrink-0 text-gold" /><div><h3 className="font-semibold group-hover:text-gold">{item.title} <span aria-hidden="true">↗</span></h3><p className="mt-1 text-sm leading-6 text-text-muted">{item.text}</p></div>
                </Link>
              ))}
            </div>
            <Link href="/tools" className="mt-8 inline-flex items-center gap-2 text-sm font-semibold text-gold hover:underline">Explore the creator tools <ArrowRight aria-hidden="true" className="size-4" /></Link>
          </div>
        </section>

        <section className="border-y border-border bg-surface px-6 py-20">
          <div className="mx-auto max-w-6xl">
            <div className="mb-10 flex flex-wrap items-end justify-between gap-6"><div><p className="marketing-eyebrow">04 / See you on the map</p><h2 className="mt-4 text-4xl font-black tracking-tight">Three steps to your first match.</h2></div><Link href="/download" className="marketing-button-primary">Get the launcher <Download aria-hidden="true" className="size-4" /></Link></div>
            <PlaySteps />
          </div>
        </section>

        <section className="mx-auto max-w-4xl px-6 py-20 md:py-24">
          <p className="marketing-eyebrow">A few things before you drop in</p>
          <h2 className="mb-9 mt-4 text-3xl font-black tracking-tight md:text-4xl">Campaign Evolved multiplayer, explained.</h2>
          <MultiplayerFaq compact />
          <Link href={MULTIPLAYER_PATH + "#faq"} className="mt-7 inline-flex items-center gap-2 text-sm font-semibold text-gold hover:underline">All multiplayer FAQs &amp; setup details <ArrowRight aria-hidden="true" className="size-4" /></Link>
        </section>
        <CommunityCallout />
      </main>
      <Footer />
    </>
  );
}
