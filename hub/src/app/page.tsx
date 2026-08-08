import type { Metadata } from "next";
import Link from "next/link";
import {
  ArrowRight,
  BookOpen,
  Braces,
  Download,
  FileCode2,
  GitMerge,
  Rocket,
  ShieldCheck,
  Terminal,
} from "lucide-react";
import { Navbar } from "./components/Navbar";
import { Footer } from "./components/Footer";
import { DiscordIcon, GitHubIcon } from "./components/icons";

export const metadata: Metadata = {
  alternates: { canonical: "https://mjolnircore.com" },
  description:
    "The open-source modding framework for Halo Campaign Evolved: a one-click mod launcher, a Guerilla-style tag editor for the game's own data, and the mjolnir command line — with a hub for signed mods.",
};

/* ── Hero ─────────────────────────────────────────────────────────────── */

/**
 * The commands and numbers here are real: validate/roundtrip figures come
 * from the README, the poke example from the tag editing guide. Anything
 * shown as output is the summary those runs actually establish.
 */
function TerminalCard() {
  return (
    <div className="glass rounded-2xl overflow-hidden text-left shadow-2xl shadow-black/40">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-border bg-surface-raised/60">
        <span className="w-3 h-3 rounded-full bg-accent-red/60" />
        <span className="w-3 h-3 rounded-full bg-gold/60" />
        <span className="w-3 h-3 rounded-full bg-accent-green/60" />
        <span className="ml-2 text-xs text-text-dim font-mono">mjolnir — powershell</span>
      </div>
      <div className="p-5 font-mono text-[13px] leading-6 overflow-x-auto">
        <p>
          <span className="text-accent-green">$</span>{" "}
          <span className="text-foreground">mjolnir validate --all</span>
        </p>
        <p className="text-text-muted">
          12,290 tags · every invariant holds · 99.9% of values decode
        </p>
        <p className="mt-4">
          <span className="text-accent-green">$</span>{" "}
          <span className="text-foreground">
            mjolnir poke --group biped --tag spartans{" "}
            <span className="whitespace-nowrap">--field &quot;jump velocity&quot; --value 25</span>
          </span>
        </p>
        <p className="text-text-muted">
          9.0 <span className="text-gold">→</span> 25.0 · written into the{" "}
          <span className="text-foreground">running game</span> · nothing on disk
        </p>
        <p className="mt-4">
          <span className="text-accent-green">$</span>{" "}
          <span className="text-foreground">mjolnir roundtrip --all</span>
        </p>
        <p className="text-text-muted">
          12,281 / 12,281 re-serialise <span className="text-accent-green">byte-exact</span> · 5.77 GB
        </p>
      </div>
    </div>
  );
}

function HeroSection() {
  return (
    <section className="hero-gradient relative pt-28 md:pt-40 pb-20 md:pb-24 px-6 overflow-hidden">
      {/* Decorative grid */}
      <div
        className="absolute inset-0 opacity-[0.03]"
        style={{
          backgroundImage:
            "linear-gradient(#d4a843 1px, transparent 1px), linear-gradient(90deg, #d4a843 1px, transparent 1px)",
          backgroundSize: "60px 60px",
        }}
      />

      <div className="relative max-w-6xl mx-auto">
        <div className="grid grid-cols-1 lg:grid-cols-[1.1fr_1fr] gap-12 lg:gap-10 items-center">
          <div className="text-center lg:text-left">
            <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-surface-raised border border-border mb-8">
              <span className="w-2 h-2 rounded-full bg-accent-green animate-pulse" />
              <span className="text-xs text-text-muted font-medium">
                Open Source Modding Framework
              </span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-gold/15 text-gold font-bold uppercase tracking-wider">
                Alpha
              </span>
            </div>

            <h1 className="text-4xl sm:text-5xl md:text-6xl font-black tracking-tight mb-6 leading-[1.08]">
              Mod Halo Campaign Evolved{" "}
              <span className="text-gold glow-text whitespace-nowrap">down to the tags</span>
            </h1>

            <p className="text-lg md:text-xl text-text-muted max-w-2xl mx-auto lg:mx-0 mb-10 leading-relaxed">
              <span className="text-foreground font-medium">MJOLNIR</span> reads the game&apos;s
              own data and hands it to you: a launcher that installs signed mods in one click,
              a Guerilla-style tag editor, and a command line that proves every byte.
            </p>

            <div className="flex flex-col sm:flex-row items-center lg:justify-start justify-center gap-4">
              <Link
                href="/download"
                className="group px-8 py-4 rounded-xl font-bold text-base bg-gradient-to-r from-gold to-gold-dim text-background hover:brightness-110 transition-all shadow-lg shadow-gold/20 glow-gold flex items-center gap-3"
              >
                <Download className="w-5 h-5" />
                Download Launcher
              </Link>
              <Link
                href="/mods"
                className="px-8 py-4 rounded-xl font-bold text-base border border-border-bright text-text-muted hover:text-foreground hover:border-gold/40 transition-all flex items-center gap-2"
              >
                Browse Mods
                <ArrowRight className="w-4 h-4" />
              </Link>
            </div>

            <div className="flex items-center lg:justify-start justify-center gap-6 sm:gap-12 mt-12">
              {[
                { value: "7", label: "Runtime Mods" },
                { value: "101", label: "Tag Groups" },
                { value: "MIT", label: "Licensed" },
              ].map((stat) => (
                <div key={stat.label} className="text-center lg:text-left">
                  <div className="text-2xl font-black text-gold">{stat.value}</div>
                  <div className="text-xs text-text-dim mt-1 uppercase tracking-wider">
                    {stat.label}
                  </div>
                </div>
              ))}
            </div>
          </div>

          <TerminalCard />
        </div>
      </div>
    </section>
  );
}

/* ── Proof strip ──────────────────────────────────────────────────────── */

const proofStats = [
  {
    value: "12,290",
    label: "shipped tags validated",
    detail: "every structural invariant, one command",
  },
  {
    value: "12,281 / 12,281",
    label: "byte-exact roundtrips",
    detail: "re-serialised and compared over 5.77 GB",
  },
  {
    value: "4,787",
    label: "textures decode",
    detail: "of 4,844 — the rest ship no pixel data",
  },
  {
    value: "13 / 13",
    label: "mission scripts recompile",
    detail: "HSC source, byte-for-byte back into the tag",
  },
];

function ProofSection() {
  return (
    <section className="py-16 px-6 bg-surface border-y border-border">
      <div className="max-w-6xl mx-auto">
        <p className="text-center text-xs font-bold uppercase tracking-widest text-text-dim mb-10">
          Measured, not promised — every number is a command you can run
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-8">
          {proofStats.map((stat) => (
            <div key={stat.label} className="text-center">
              <div className="text-3xl font-black text-gold whitespace-nowrap">{stat.value}</div>
              <div className="text-sm font-semibold text-foreground mt-2">{stat.label}</div>
              <div className="text-xs text-text-dim mt-1">{stat.detail}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ── Toolchain ────────────────────────────────────────────────────────── */

const toolchain = [
  {
    title: "MJOLNIR Launcher",
    chip: { label: "Download", className: "bg-accent-green/10 text-accent-green" },
    description:
      "One-click installs for mods and tools. Auto-detects your game, verifies every download against its published hash, and installs nothing that fails signature verification.",
    icon: <Rocket className="w-6 h-6" />,
    href: "/download",
    cta: "Get the launcher",
  },
  {
    title: "Tag Editor",
    chip: { label: "Download", className: "bg-accent-green/10 text-accent-green" },
    description:
      "Guerilla, reborn. Browse every tag with decoded values, export textures as PNG, play the ~6 GB of named Wwise audio, edit mission scripts that recompile — and write edits into the running game with Live mode.",
    icon: <FileCode2 className="w-6 h-6" />,
    href: "/tools/tag-editor",
    cta: "See the editor",
  },
  {
    title: "mjolnir CLI",
    chip: { label: "Build from source", className: "bg-accent-blue/10 text-accent-blue" },
    description:
      "The same tag engine from a shell. List and search groups, set a field by its dotted path, pack an override container, poke the live process — and validate the whole install when you're done.",
    icon: <Terminal className="w-6 h-6" />,
    href: "/tools/mjolnir-cli",
    cta: "See the CLI",
  },
];

function ToolchainSection() {
  return (
    <section className="py-24 px-6">
      <div className="max-w-6xl mx-auto">
        <div className="text-center mb-16">
          <h2 className="text-3xl md:text-4xl font-black text-foreground mb-4">
            One framework, three ways in
          </h2>
          <p className="text-text-muted text-lg max-w-2xl mx-auto">
            Play with mods, make your own, or script the whole pipeline — each tool reads your
            installed copy of the game directly. Nothing shipped is ever modified.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {toolchain.map((tool) => (
            <Link
              key={tool.title}
              href={tool.href}
              className="glass rounded-2xl p-6 hover:border-gold/20 transition-all duration-300 group flex flex-col"
            >
              <div className="flex items-center justify-between mb-4">
                <div className="w-12 h-12 rounded-xl bg-gold/10 text-gold flex items-center justify-center group-hover:bg-gold/20 transition-colors">
                  {tool.icon}
                </div>
                <span
                  className={`rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider ${tool.chip.className}`}
                >
                  {tool.chip.label}
                </span>
              </div>
              <h3 className="text-lg font-bold text-foreground mb-2">{tool.title}</h3>
              <p className="text-sm text-text-muted leading-relaxed mb-5">{tool.description}</p>
              <span className="mt-auto inline-flex items-center gap-1.5 text-sm font-semibold text-gold">
                {tool.cta}
                <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-0.5" />
              </span>
            </Link>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ── Showcase ─────────────────────────────────────────────────────────── */

const showcase = [
  {
    src: "/docs-images/ammo-magazine-99.jpg",
    alt: "Halo Campaign Evolved HUD showing a 99-round assault rifle magazine",
    title: "One field edit",
    caption:
      "rounds loaded maximum set to 99 in the tag editor, baked into an override container the game loads beside the shipped ones — and read straight off the HUD.",
    href: "/docs/guides/making-your-first-mod",
    cta: "Make your first mod",
  },
  {
    src: "/docs-images/texture_swap_assault_rifle.jpg",
    alt: "Assault rifle re-textured red in Halo Campaign Evolved",
    title: "One texture swap",
    caption:
      "A PNG re-encoded to the exact size the game shipped, so the override replaces one chunk of one file and moves no metadata. The rifle comes out red.",
    href: "/docs/guides/texture-swapping",
    cta: "How texture swapping works",
  },
];

function ShowcaseSection() {
  return (
    <section className="py-24 px-6 bg-surface">
      <div className="max-w-6xl mx-auto">
        <div className="text-center mb-16">
          <h2 className="text-3xl md:text-4xl font-black text-foreground mb-4">
            Make a change. See it in the game.
          </h2>
          <p className="text-text-muted text-lg max-w-2xl mx-auto">
            These are unedited screenshots of edits made with the tools on this site — the same
            walkthroughs are in the docs.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {showcase.map((item) => (
            <div
              key={item.title}
              className="rounded-2xl overflow-hidden border border-border bg-surface-raised flex flex-col"
            >
              {/* Plain <img>: these live in /public and ship as-is. */}
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={item.src}
                alt={item.alt}
                loading="lazy"
                className="w-full aspect-video object-cover border-b border-border"
              />
              <div className="p-6 flex flex-col flex-1">
                <h3 className="text-lg font-bold text-foreground mb-2">{item.title}</h3>
                <p className="text-sm text-text-muted leading-relaxed mb-4">{item.caption}</p>
                <Link
                  href={item.href}
                  className="mt-auto inline-flex items-center gap-1.5 text-sm font-semibold text-gold hover:underline"
                >
                  {item.cta}
                  <ArrowRight className="w-4 h-4" />
                </Link>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ── Runtime mods ─────────────────────────────────────────────────────── */

const runtimeMods = [
  { name: "MJOLNIRFlyCam", blurb: "Free-flying detached camera on the numpad, with mouse look, speed boost and HUD toggle." },
  { name: "MJOLNIRConsoleEnabler", blurb: "The full UE5 developer console, enabled in the shipping build." },
  { name: "MJOLNIRTagProbe", blurb: "Read the Blam tag assets the game actually loaded — not what you inferred it would." },
  { name: "MJOLNIRBridge", blurb: "Drive the game from outside: run Lua and console commands, read state, take screenshots." },
  { name: "MJOLNIRMultiplayer", blurb: "Experimental map travel, listen-server loading and player administration probes." },
  { name: "MJOLNIRDiscovery", blurb: "UFunction dumper and travel logging for charting the engine as it runs." },
];

function RuntimeModsSection() {
  return (
    <section className="py-24 px-6">
      <div className="max-w-6xl mx-auto">
        <div className="text-center mb-16">
          <h2 className="text-3xl md:text-4xl font-black text-foreground mb-4">
            And a framework inside the running game
          </h2>
          <p className="text-text-muted text-lg max-w-2xl mx-auto">
            Seven UE4SS Lua mods ship with MJOLNIR — MJOLNIRCore is the runtime, and these stand
            on it. All installed and updated by the launcher.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {runtimeMods.map((mod) => (
            <div
              key={mod.name}
              className="rounded-xl border border-border bg-surface-raised p-5 hover:border-gold/20 transition-colors"
            >
              <h3 className="font-mono text-sm font-bold text-gold mb-2">{mod.name}</h3>
              <p className="text-sm text-text-muted leading-relaxed">{mod.blurb}</p>
            </div>
          ))}
        </div>

        <p className="text-center mt-8">
          <Link
            href="https://github.com/devnull9090/mjolnir-core"
            target="_blank"
            className="inline-flex items-center gap-2 text-sm font-semibold text-text-muted hover:text-foreground transition-colors"
          >
            <GitHubIcon className="w-4 h-4" />
            All of it is MIT-licensed source
            <ArrowRight className="w-4 h-4" />
          </Link>
        </p>
      </div>
    </section>
  );
}

/* ── Platform ─────────────────────────────────────────────────────────── */

const platform = [
  {
    title: "Signed all the way through",
    description:
      "Authors publish from the tag editor with a per-device Ed25519 key, over an account link made by device pairing. The launcher and CLI verify every archive; unsigned builds never install.",
    icon: <ShieldCheck className="w-6 h-6" />,
    href: "/mods",
    cta: "Browse mods",
  },
  {
    title: "Conflicts, computed",
    description:
      "A content mod's chunk IDs are identical to the tags it overrides, so “do these mods conflict?” is an exact set intersection — checked by the hub, not declared by the author.",
    icon: <GitMerge className="w-6 h-6" />,
    href: "/docs/api",
    cta: "POST /api/v1/conflicts/check",
  },
  {
    title: "An open API",
    description:
      "Spec-first OpenAPI 3.1, generated from the same schemas that validate requests — CI fails if they drift. Reads need no key and CORS is open, so build against it.",
    icon: <Braces className="w-6 h-6" />,
    href: "/docs/api",
    cta: "Read the API reference",
  },
  {
    title: "The format, documented",
    description:
      "A searchable reference of all 101 tag groups — 1,779 structs, 13,250 fields — plus the research notes behind every format MJOLNIR reads: tags, textures, audio, scripts, containers.",
    icon: <BookOpen className="w-6 h-6" />,
    href: "/docs/tags",
    cta: "Search the tag reference",
  },
];

function PlatformSection() {
  return (
    <section className="py-24 px-6 bg-surface">
      <div className="max-w-6xl mx-auto">
        <div className="text-center mb-16">
          <h2 className="text-3xl md:text-4xl font-black text-foreground mb-4">
            A hub that takes mods seriously
          </h2>
          <p className="text-text-muted text-lg max-w-2xl mx-auto">
            mjolnircore.com is part of the framework: distribution, verification and
            documentation, built on the same primitives as the tools.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {platform.map((item) => (
            <Link
              key={item.title}
              href={item.href}
              className="glass rounded-2xl p-6 hover:border-gold/20 transition-all duration-300 group flex flex-col"
            >
              <div className="w-12 h-12 rounded-xl bg-gold/10 text-gold flex items-center justify-center mb-4 group-hover:bg-gold/20 transition-colors">
                {item.icon}
              </div>
              <h3 className="text-lg font-bold text-foreground mb-2">{item.title}</h3>
              <p className="text-sm text-text-muted leading-relaxed mb-5">{item.description}</p>
              <span className="mt-auto inline-flex items-center gap-1.5 text-sm font-semibold text-gold font-mono">
                {item.cta}
                <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-0.5" />
              </span>
            </Link>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ── Getting started ──────────────────────────────────────────────────── */

const steps = [
  {
    number: "1",
    title: "Download the launcher",
    description: "It auto-detects your Halo Campaign Evolved install and sets up the runtime.",
    href: "/download",
    cta: "Download",
  },
  {
    number: "2",
    title: "Pick your mods",
    description: "One click to install — signed, hash-verified and conflict-checked on the way in.",
    href: "/mods",
    cta: "Browse mods",
  },
  {
    number: "3",
    title: "Make your own",
    description:
      "Install the tag editor from the launcher's Tools tab and follow the first-mod guide.",
    href: "/docs/guides/making-your-first-mod",
    cta: "Read the guide",
  },
];

function GettingStartedSection() {
  return (
    <section className="py-24 px-6">
      <div className="max-w-6xl mx-auto">
        <div className="text-center mb-16">
          <h2 className="text-3xl md:text-4xl font-black text-foreground mb-4">
            Up and modding in minutes
          </h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {steps.map((step) => (
            <Link
              key={step.number}
              href={step.href}
              className="rounded-2xl border border-border bg-surface-raised p-6 hover:border-gold/40 transition-colors group"
            >
              <div className="w-10 h-10 rounded-full bg-gold/15 text-gold font-black flex items-center justify-center mb-4">
                {step.number}
              </div>
              <h3 className="text-lg font-bold text-foreground mb-2">{step.title}</h3>
              <p className="text-sm text-text-muted leading-relaxed mb-4">{step.description}</p>
              <span className="inline-flex items-center gap-1.5 text-sm font-semibold text-gold">
                {step.cta}
                <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-0.5" />
              </span>
            </Link>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ── CTA ──────────────────────────────────────────────────────────────── */

function CTASection() {
  return (
    <section className="py-24 px-6 bg-surface border-t border-border">
      <div className="max-w-3xl mx-auto text-center">
        <h2 className="text-3xl md:text-4xl font-black text-foreground mb-6">Ready to Forge?</h2>
        <p className="text-lg text-text-muted mb-10 max-w-xl mx-auto">
          Download the launcher, install your first mod, and join the MJOLNIR community on
          Discord.
        </p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
          <Link
            href="/download"
            className="px-8 py-4 rounded-xl font-bold bg-gradient-to-r from-gold to-gold-dim text-background hover:brightness-110 transition-all shadow-lg shadow-gold/20 flex items-center gap-2"
          >
            <Download className="w-5 h-5" />
            Download Launcher
          </Link>
          <Link
            href="https://discord.gg/9gxYZsByW9"
            target="_blank"
            className="px-8 py-4 rounded-xl font-bold border border-border-bright text-text-muted hover:text-foreground hover:border-accent-blue/40 transition-all flex items-center gap-2"
          >
            <DiscordIcon />
            Join Discord
          </Link>
        </div>
      </div>
    </section>
  );
}

/* ── Page ──────────────────────────────────────────────────────────────── */

export default function Home() {
  // The launcher is the thing this page offers; describing it as an
  // application is what earns a rich result, same as the tool pages do.
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    name: "MJOLNIR Launcher",
    operatingSystem: "Windows 10, Windows 11",
    applicationCategory: "UtilitiesApplication",
    offers: { "@type": "Offer", price: "0", priceCurrency: "USD" },
    url: "https://mjolnircore.com",
    downloadUrl: "https://mjolnircore.com/download",
    license: "https://github.com/devnull9090/mjolnir-core/blob/main/LICENSE",
  };

  return (
    <>
      <Navbar />
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      <main className="flex-1">
        <HeroSection />
        <ProofSection />
        <ToolchainSection />
        <ShowcaseSection />
        <RuntimeModsSection />
        <PlatformSection />
        <GettingStartedSection />
        <CTASection />
      </main>
      <Footer />
    </>
  );
}
