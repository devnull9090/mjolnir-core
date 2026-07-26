import Link from "next/link";

function MjolnirIcon() {
  return (
    <svg viewBox="0 0 32 32" className="w-8 h-8" fill="none">
      <path
        d="M16 2L4 10v12l12 8 12-8V10L16 2z"
        stroke="currentColor"
        strokeWidth="1.5"
        className="text-gold"
      />
      <path
        d="M16 6l-8 5.5v11L16 28l8-5.5v-11L16 6z"
        fill="currentColor"
        className="text-gold/20"
      />
      <path d="M16 12v8M12 16h8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" className="text-gold" />
    </svg>
  );
}

function Navbar() {
  return (
    <nav className="fixed top-0 left-0 right-0 z-50 border-b border-border/50 bg-background/60 backdrop-blur-xl">
      <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-3">
          <MjolnirIcon />
          <span className="text-lg font-bold tracking-wide text-gold">MJOLNIR</span>
          <span className="text-xs text-text-muted font-medium">CORE</span>
        </Link>
        <div className="hidden md:flex items-center gap-8">
          <Link href="/mods" className="text-sm text-text-muted hover:text-foreground transition-colors">
            Mods
          </Link>
          <Link href="https://discord.gg/9gxYZsByW9" target="_blank" className="text-sm text-text-muted hover:text-foreground transition-colors">
            Discord
          </Link>
          <Link href="https://github.com/devnull9090/mjolnir-core" target="_blank" className="text-sm text-text-muted hover:text-foreground transition-colors">
            GitHub
          </Link>
          <Link
            href="https://releases.mjolnircore.com/launcher/latest"
            className="px-4 py-2 text-sm font-semibold rounded-lg bg-gold text-background hover:brightness-110 transition-all"
          >
            Download Launcher
          </Link>
        </div>
      </div>
    </nav>
  );
}

function HeroSection() {
  return (
    <section className="hero-gradient relative pt-32 pb-24 px-6 overflow-hidden">
      {/* Decorative grid */}
      <div className="absolute inset-0 opacity-[0.03]" style={{
        backgroundImage: "linear-gradient(#d4a843 1px, transparent 1px), linear-gradient(90deg, #d4a843 1px, transparent 1px)",
        backgroundSize: "60px 60px"
      }} />

      <div className="relative max-w-5xl mx-auto text-center">
        <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full bg-surface-raised border border-border mb-8">
          <span className="w-2 h-2 rounded-full bg-accent-green animate-pulse" />
          <span className="text-xs text-text-muted font-medium">Open Source Modding Framework</span>
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
            href="https://releases.mjolnircore.com/launcher/latest"
            className="group px-8 py-4 rounded-xl font-bold text-base bg-gradient-to-r from-gold to-gold-dim text-background hover:brightness-110 transition-all shadow-lg shadow-gold/20 glow-gold flex items-center gap-3"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            Download Launcher
          </Link>
          <Link
            href="/mods"
            className="px-8 py-4 rounded-xl font-bold text-base border border-border-bright text-text-muted hover:text-foreground hover:border-gold/40 transition-all"
          >
            Browse Mods →
          </Link>
        </div>

        {/* Stats */}
        <div className="flex items-center justify-center gap-12 mt-16">
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

const features = [
  {
    title: "FlyCam",
    description: "Smooth free-flying debug camera with WASD movement, mouse viewport look, speed boost, and auto HUD toggle.",
    icon: (
      <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
      </svg>
    ),
  },
  {
    title: "Developer Console",
    description: "Full UE5 developer console enabled in the shipping build via dwmapi.dll proxy and custom UE4SS signatures.",
    icon: (
      <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
      </svg>
    ),
  },
  {
    title: "Mod Launcher",
    description: "One-click desktop app to install, manage, and update mods. Auto-detects your HCE installation.",
    icon: (
      <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z" />
      </svg>
    ),
  },
  {
    title: "Community Hub",
    description: "Browse, download, and share mods with the community. Discord integration and player tracking coming soon.",
    icon: (
      <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
      </svg>
    ),
  },
  {
    title: "Hot Reload",
    description: "Press CTRL+R in-game to instantly reload all Lua mods without restarting. Iterate at the speed of thought.",
    icon: (
      <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
      </svg>
    ),
  },
  {
    title: "Open Source",
    description: "MIT licensed. Reverse-engineered with Ghidra, built with UE4SS, and driven by the community.",
    icon: (
      <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
      </svg>
    ),
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

function HotkeysSection() {
  const hotkeys = [
    { key: "F8", action: "Toggle FlyCam ON/OFF" },
    { key: "F7", action: "Toggle HUD overlay" },
    { key: "F9", action: "Toggle mouse look" },
    { key: "CTRL+R", action: "Hot reload all mods" },
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
            href="https://releases.mjolnircore.com/launcher/latest"
            className="px-8 py-4 rounded-xl font-bold bg-gradient-to-r from-gold to-gold-dim text-background hover:brightness-110 transition-all shadow-lg shadow-gold/20"
          >
            Download Launcher
          </Link>
          <Link
            href="https://discord.gg/9gxYZsByW9"
            target="_blank"
            className="px-8 py-4 rounded-xl font-bold border border-border-bright text-text-muted hover:text-foreground hover:border-accent-blue/40 transition-all flex items-center gap-2"
          >
            <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
              <path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028c.462-.63.874-1.295 1.226-1.994a.076.076 0 0 0-.041-.106 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03z" />
            </svg>
            Join Discord
          </Link>
        </div>
      </div>
    </section>
  );
}

function Footer() {
  return (
    <footer className="py-8 px-6 border-t border-border">
      <div className="max-w-6xl mx-auto flex flex-col md:flex-row items-center justify-between gap-4">
        <div className="flex items-center gap-2 text-sm text-text-dim">
          <MjolnirIcon />
          <span>MJOLNIR Core — MIT Licensed</span>
        </div>
        <div className="flex items-center gap-6 text-sm text-text-dim">
          <Link href="https://github.com/devnull9090/mjolnir-core" target="_blank" className="hover:text-foreground transition-colors">
            GitHub
          </Link>
          <Link href="https://discord.gg/9gxYZsByW9" target="_blank" className="hover:text-foreground transition-colors">
            Discord
          </Link>
          <Link href="/mods" className="hover:text-foreground transition-colors">
            Mods
          </Link>
        </div>
      </div>
    </footer>
  );
}

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
