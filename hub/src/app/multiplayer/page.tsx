import Link from "next/link";
import { ArrowRight, Download, ExternalLink } from "lucide-react";
import { Navbar } from "../components/Navbar";
import { Footer } from "../components/Footer";
import { CommunityCallout, MultiplayerFaq, PlaySteps } from "../components/MultiplayerMarketing";
import {
  CLASSIC_MAPS,
  MULTIPLAYER_FAQS,
  MULTIPLAYER_IMAGES,
  MULTIPLAYER_PATH,
  MULTIPLAYER_RELEASE_PATH,
  SITE_URL,
  marketingMetadata,
} from "@/lib/marketing";

export const metadata = marketingMetadata(
  "Halo Campaign Evolved Multiplayer Mod, Maps & FAQ | MJOLNIR",
  "Does Halo Campaign Evolved have multiplayer? Yes, with MJOLNIR Core. Play Slayer and CTF on all 19 classic Halo CE maps. Get setup steps, requirements, and FAQs.",
  MULTIPLAYER_PATH,
);

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

export default function MultiplayerPage() {
  return (
    <>
      <Navbar />
      <main className="marketing">
        <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(faqSchema).replace(/</g, "\\u003c") }} />
        <section className="border-b border-border px-6 pb-16 pt-40 md:pt-48">
          <div className="mx-auto grid max-w-6xl items-center gap-10 lg:grid-cols-[1.1fr_1fr]">
            <div>
              <p className="marketing-eyebrow">MJOLNIR Core / Multiplayer alpha</p>
              <h1 className="mt-5 text-4xl font-black leading-[1.08] tracking-tight sm:text-5xl lg:text-6xl">Halo Campaign Evolved.<br /><span className="text-gold">Now with classic multiplayer.</span></h1>
              <p className="mt-6 text-lg leading-8 text-text-muted">Looking for Campaign Evolved multiplayer? MJOLNIR Core is the community-made modding framework that brings Slayer, Capture the Flag, and all 19 classic Halo CE maps to your game.</p>
              <div className="mt-8 flex flex-col gap-3 sm:flex-row">
                <Link href="/download" className="marketing-button-primary"><Download aria-hidden="true" className="size-4" /> Get the multiplayer launcher</Link>
                <a href="#setup" className="marketing-button-secondary">How to play <ArrowRight aria-hidden="true" className="size-4" /></a>
              </div>
              <p className="mt-5 text-xs leading-6 text-text-muted">Community mod · Free &amp; open source · Your own copy of the game required</p>
            </div>
            <figure className="border border-border bg-surface p-3">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={MULTIPLAYER_IMAGES.bloodGulch} alt="Blood Gulch running in Halo Campaign Evolved through MJOLNIR Core" fetchPriority="high" width={960} height={720} className="aspect-[4/3] w-full object-cover" />
              <figcaption className="px-2 pb-2 pt-4 font-mono text-[10px] uppercase tracking-widest text-text-muted">Blood Gulch / Captured in Campaign Evolved</figcaption>
            </figure>
          </div>
        </section>

        <section className="mx-auto max-w-6xl px-6 py-16">
          <div className="grid gap-10 lg:grid-cols-[1.1fr_1fr] lg:gap-20">
            <div>
              <p className="marketing-eyebrow">The answer you came for</p>
              <h2 className="mt-4 text-3xl font-black tracking-tight">Does Halo Campaign Evolved have multiplayer?</h2>
              <p className="mt-5 text-lg leading-8"><strong className="text-gold">With MJOLNIR Core, it does.</strong> Install our multiplayer mod to play classic competitive Halo with your friends inside Campaign Evolved.</p>
              <p className="mt-4 leading-7 text-text-muted">Get the original maps, a multiplayer lobby, a kill feed, a scoreboard, and team-aware HUD elements. Slayer and CTF are available across the classic collection, with framework support for Team Slayer, King of the Hill, and Oddball when the map and installed variant support them.</p>
            </div>
            <aside className="border-l-2 border-gold bg-surface p-6 sm:p-8">
              <h3 className="text-lg font-bold">What to know about the alpha</h3>
              <ul className="mt-4 space-y-3 text-sm leading-7 text-text-muted">
                <li>Up to four players in a fireteam.</li>
                <li>Built and tested on Windows with the Steam version. Game Pass is not yet verified.</li>
                <li>Everyone needs the same maps installed.</li>
                <li>Community-made multiplayer, separate from official campaign and co-op features.</li>
              </ul>
              <Link href={MULTIPLAYER_RELEASE_PATH} className="mt-5 inline-flex items-center gap-2 text-sm font-semibold text-gold hover:underline">Read the alpha announcement <ArrowRight aria-hidden="true" className="size-4" /></Link>
            </aside>
          </div>
        </section>

        <section id="setup" className="scroll-mt-32 border-y border-border bg-surface px-6 py-16 md:py-20">
          <div className="mx-auto max-w-6xl">
            <p className="marketing-eyebrow">From download to drop-in</p>
            <h2 className="mb-10 mt-4 text-3xl font-black tracking-tight md:text-4xl">How to play Campaign Evolved multiplayer</h2>
            <PlaySteps />
            <div className="mt-8 flex flex-wrap gap-6 text-sm font-semibold text-gold">
              <Link href="/download" className="inline-flex items-center gap-2 hover:underline">Download &amp; requirements <ArrowRight aria-hidden="true" className="size-4" /></Link>
              <Link href="/games" className="inline-flex items-center gap-2 hover:underline">View reported games <ArrowRight aria-hidden="true" className="size-4" /></Link>
            </div>
          </div>
        </section>

        <section className="mx-auto max-w-6xl px-6 py-16 md:py-20">
          <p className="marketing-eyebrow">The full classic collection</p>
          <h2 className="mt-4 text-3xl font-black tracking-tight md:text-4xl">All 19 original Halo CE multiplayer maps.</h2>
          <p className="mt-5 max-w-2xl leading-7 text-text-muted">The original Xbox arenas and the Halo PC additions, together in Campaign Evolved. Install the collection from the launcher, or explore each map below.</p>
          <ul className="mt-8 grid grid-cols-1 gap-x-8 sm:grid-cols-2 lg:grid-cols-3">
            {CLASSIC_MAPS.map((map) => (
              <li key={map.slug} className="border-b border-border"><Link href={"/mods/" + map.slug} className="flex items-center justify-between gap-4 py-4 text-sm font-medium hover:text-gold">{map.name}<ArrowRight aria-hidden="true" className="size-4 text-text-muted" /></Link></li>
            ))}
          </ul>
        </section>

        <section className="border-y border-border bg-surface px-6 py-16">
          <div className="mx-auto grid max-w-6xl gap-8 md:grid-cols-2 md:gap-16">
            <div><p className="marketing-eyebrow">A framework to build on</p><h2 className="mt-4 text-3xl font-black tracking-tight">Make custom maps and content.</h2><p className="mt-5 leading-7 text-text-muted">Use the Blender addon, custom level pipeline, tag editor, and CLI to build your own worlds and change the way they play. Start with a weapon or texture edit, then work toward a map of your own.</p></div>
            <div className="flex flex-col justify-center gap-4">
              {[
                { href: "/docs/guides/level-authoring", label: "Create a custom level" },
                { href: "/docs/notes/ce-map-conversion", label: "Explore classic map conversion" },
                { href: "/docs/guides/making-your-first-mod", label: "Make your first content mod" },
                { href: "/docs/notes/map-distribution", label: "Package and publish a map" },
              ].map((item) => <Link key={item.href} href={item.href} className="flex items-center justify-between gap-4 border-b border-border pb-4 text-sm font-semibold text-gold hover:text-foreground">{item.label}<ExternalLink aria-hidden="true" className="size-4" /></Link>)}
            </div>
          </div>
        </section>

        <section id="faq" className="mx-auto max-w-4xl scroll-mt-32 px-6 py-16 md:py-24">
          <p className="marketing-eyebrow">Before your first match</p>
          <h2 className="mb-9 mt-4 text-3xl font-black tracking-tight md:text-4xl">Campaign Evolved multiplayer FAQ</h2>
          <MultiplayerFaq />
        </section>
        <CommunityCallout />
      </main>
      <Footer />
    </>
  );
}
