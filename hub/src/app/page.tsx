import Link from "next/link";
import {
  Download,
  Video,
  Terminal,
  Sparkles,
  Users,
  RefreshCw,
  Code,
  ArrowRight,
} from "lucide-react";
import { Navbar } from "./components/Navbar";
import { Footer } from "./components/Footer";

/* ── Hero ─────────────────────────────────────────────────────────────── */

function HeroSection() {
  return (
    <section className="hero-gradient relative pt-32 md:pt-44 pb-24 px-6 overflow-hidden">
      {/* Decorative grid */}
      <div className="absolute inset-0 opacity-[0.03]" style={{
        backgroundImage: "linear-gradient(#d4a843 1px, transparent 1px), linear-gradient(90deg, #d4a843 1px, transparent 1px)",
        backgroundSize: "60px 60px"
      }} />

      <div className="relative max-w-5xl mx-auto text-center">
        <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-surface-raised border border-border mb-8">
          <span className="w-2 h-2 rounded-full bg-accent-green animate-pulse" />
          <span className="text-xs text-text-muted font-medium">Open Source Modding Framework</span>
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-gold/15 text-gold font-bold uppercase tracking-wider">Alpha</span>
        </div>

        <h1 className="text-5xl md:text-7xl font-black tracking-tight mb-6 leading-[1.1]">
          <span className="text-gold glow-text">MJOLNIR</span>{" "}
          <span className="text-foreground">Core</span>
        </h1>

        <p className="text-lg md:text-xl text-text-muted max-w-2xl mx-auto mb-10 leading-relaxed">
          The modding platform for{" "}
          <span className="text-foreground font-medium">Halo Campaign Evolved</span>.
          Free camera, console commands, mod management, and a community hub — all open source.
        </p>

        <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
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

        {/* Stats */}
        <div className="flex items-center justify-center gap-6 sm:gap-12 mt-16">
          {[
            { value: "5", label: "Official Mods" },
            { value: "MIT", label: "Licensed" },
            { value: "UE5", label: "Engine" },
          ].map((stat) => (
            <div key={stat.label} className="text-center">
              <div className="text-2xl font-black text-gold">{stat.value}</div>
              <div className="text-xs text-text-dim mt-1 uppercase tracking-wider">{stat.label}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ── Features ─────────────────────────────────────────────────────────── */

const features = [
  {
    title: "FlyCam",
    description: "Smooth free-flying debug camera with WASD movement, mouse viewport look, speed boost, and auto HUD toggle.",
    icon: <Video className="w-6 h-6" />,
  },
  {
    title: "Developer Console",
    description: "Full UE5 developer console enabled in the shipping build via dwmapi.dll proxy and custom UE4SS signatures.",
    icon: <Terminal className="w-6 h-6" />,
  },
  {
    title: "Mod Launcher",
    description: "One-click desktop app to install, manage, and update mods. Auto-detects your HCE installation.",
    icon: <Sparkles className="w-6 h-6" />,
  },
  {
    title: "Community Hub",
    description: "Browse, download, and share mods with the community. Discord integration and player tracking coming soon.",
    icon: <Users className="w-6 h-6" />,
  },
  {
    title: "Runtime Discovery",
    description: "Inspect live BlamEngine variants, worlds, session state, and network components through evidence-aware console probes.",
    icon: <RefreshCw className="w-6 h-6" />,
  },
  {
    title: "Open Source",
    description: "MIT licensed. Reverse-engineered with Ghidra, built with UE4SS, and driven by the community.",
    icon: <Code className="w-6 h-6" />,
  },
];

function FeaturesSection() {
  return (
    <section className="py-24 px-6 bg-surface">
      <div className="max-w-6xl mx-auto">
        <div className="text-center mb-16">
          <h2 className="text-3xl md:text-4xl font-black text-foreground mb-4">
            Everything You Need to Mod HCE
          </h2>
          <p className="text-text-muted text-lg max-w-xl mx-auto">
            Built from the ground up for Halo Campaign Evolved&apos;s hybrid UE5 + Blam engine architecture.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {features.map((feature) => (
            <div
              key={feature.title}
              className="glass rounded-2xl p-6 hover:border-gold/20 transition-all duration-300 group"
            >
              <div className="w-12 h-12 rounded-xl bg-gold/10 text-gold flex items-center justify-center mb-4 group-hover:bg-gold/20 transition-colors">
                {feature.icon}
              </div>
              <h3 className="text-lg font-bold text-foreground mb-2">{feature.title}</h3>
              <p className="text-sm text-text-muted leading-relaxed">{feature.description}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ── Hotkeys ──────────────────────────────────────────────────────────── */

function HotkeysSection() {
  const hotkeys = [
    { key: "F8", action: "Toggle FlyCam ON/OFF" },
    { key: "F7", action: "Toggle HUD overlay" },
    { key: "F9", action: "Toggle mouse look" },
    { key: "F10", action: "Open developer console" },
    { key: "~", action: "Open developer console" },
    { key: "WASD", action: "FlyCam movement" },
  ];

  return (
    <section className="py-24 px-6">
      <div className="max-w-4xl mx-auto">
        <div className="text-center mb-12">
          <h2 className="text-3xl font-black text-foreground mb-4">Quick Reference</h2>
          <p className="text-text-muted">Default hotkeys — fully customizable</p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {hotkeys.map((hk) => (
            <div key={hk.key} className="flex items-center gap-4 p-4 rounded-xl bg-surface-raised border border-border">
              <kbd className="px-3 py-1.5 rounded-lg bg-surface-card border border-border-bright text-gold font-mono text-sm font-bold min-w-[72px] text-center">
                {hk.key}
              </kbd>
              <span className="text-sm text-text-muted">{hk.action}</span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ── CTA ──────────────────────────────────────────────────────────────── */

function DiscordIcon({ className = "w-5 h-5" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028c.462-.63.874-1.295 1.226-1.994a.076.076 0 0 0-.041-.106 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z" />
    </svg>
  );
}

function CTASection() {
  return (
    <section className="py-24 px-6 bg-surface">
      <div className="max-w-3xl mx-auto text-center">
        <h2 className="text-3xl md:text-4xl font-black text-foreground mb-6">
          Ready to Forge?
        </h2>
        <p className="text-lg text-text-muted mb-10 max-w-xl mx-auto">
          Download the launcher, install your first mod, and join the MJOLNIR community on Discord.
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
  return (
    <>
      <Navbar />
      <main className="flex-1">
        <HeroSection />
        <FeaturesSection />
        <HotkeysSection />
        <CTASection />
      </main>
      <Footer />
    </>
  );
}
