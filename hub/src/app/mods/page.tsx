import Link from "next/link";

const FEATURED_MODS = [
  {
    slug: "mjolnir-flycam",
    name: "MJOLNIRFlyCam",
    description: "Smooth free-flying debug camera with WASD movement, mouse viewport look, speed boost, and automatic HUD toggle.",
    author: "devnull9090",
    version: "1.0.0",
    downloads: 0,
    category: "camera",
  },
  {
    slug: "mjolnir-console-enabler",
    name: "MJOLNIRConsoleEnabler",
    description: "Enables the UE5 developer console in Halo Campaign Evolved's shipping build via UE4SS.",
    author: "devnull9090",
    version: "1.0.0",
    downloads: 0,
    category: "tools",
  },
  {
    slug: "mjolnir-multiplayer",
    name: "MJOLNIRMultiplayer",
    description: "Session hosting, server travel, kick/ban admin commands for multiplayer gameplay.",
    author: "devnull9090",
    version: "0.1.0",
    downloads: 0,
    category: "multiplayer",
  },
  {
    slug: "mjolnir-core",
    name: "MJOLNIRCore",
    description: "Core runtime initialization and UEHelpers utility library. Required by all MJOLNIR mods.",
    author: "devnull9090",
    version: "1.0.0",
    downloads: 0,
    category: "framework",
  },
  {
    slug: "mjolnir-discovery",
    name: "MJOLNIRDiscovery",
    description: "Diagnostic UFunction dumper and netcode travel URL logging for reverse engineering.",
    author: "devnull9090",
    version: "0.1.0",
    downloads: 0,
    category: "tools",
  },
];

const CATEGORIES = ["all", "camera", "tools", "multiplayer", "framework", "gameplay"];

export default function ModsPage() {
  return (
    <>
      {/* Navbar */}
      <nav className="fixed top-0 left-0 right-0 z-50 border-b border-border/50 bg-background/60 backdrop-blur-xl">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-3">
            <span className="text-lg font-bold tracking-wide text-gold">MJOLNIR</span>
            <span className="text-xs text-text-muted font-medium">CORE</span>
          </Link>
          <div className="flex items-center gap-6">
            <Link href="/mods" className="text-sm text-foreground font-medium">Mods</Link>
            <Link href="https://discord.gg/9gxYZsByW9" target="_blank" className="text-sm text-text-muted hover:text-foreground transition-colors">Discord</Link>
          </div>
        </div>
      </nav>

      <main className="pt-24 pb-16 px-6 max-w-6xl mx-auto">
        {/* Header */}
        <div className="mb-10">
          <h1 className="text-4xl font-black text-foreground mb-3">Mods</h1>
          <p className="text-text-muted text-lg">
            Browse and download community mods for Halo Campaign Evolved
          </p>
        </div>

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-2 mb-8">
          {CATEGORIES.map((cat) => (
            <button
              key={cat}
              className={`px-4 py-2 rounded-lg text-sm font-medium capitalize transition-all cursor-pointer
                ${cat === "all"
                  ? "bg-gold/15 text-gold border border-gold/30"
                  : "bg-surface-raised text-text-muted border border-border hover:border-border-bright hover:text-foreground"
                }`}
            >
              {cat}
            </button>
          ))}
        </div>

        {/* Mod Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {FEATURED_MODS.map((mod) => (
            <div
              key={mod.slug}
              className="group rounded-2xl bg-surface-raised border border-border hover:border-gold/20 transition-all duration-300 overflow-hidden"
            >
              {/* Card Header */}
              <div className="p-5 pb-3">
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <h3 className="text-base font-bold text-foreground group-hover:text-gold transition-colors">
                      {mod.name}
                    </h3>
                    <span className="text-xs text-text-dim">by {mod.author}</span>
                  </div>
                  <span className="px-2 py-0.5 rounded text-[10px] font-mono text-text-dim bg-surface-card border border-border">
                    v{mod.version}
                  </span>
                </div>
                <p className="text-sm text-text-muted leading-relaxed line-clamp-3">
                  {mod.description}
                </p>
              </div>

              {/* Card Footer */}
              <div className="px-5 py-3 border-t border-border/50 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span className="text-xs text-text-dim capitalize px-2 py-0.5 rounded bg-surface-card">
                    {mod.category}
                  </span>
                  <span className="text-xs text-text-dim flex items-center gap-1">
                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                    </svg>
                    {mod.downloads}
                  </span>
                </div>
                <button className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-gold/10 text-gold hover:bg-gold/20 transition-colors cursor-pointer">
                  Download
                </button>
              </div>
            </div>
          ))}
        </div>

        {/* Upload CTA */}
        <div className="mt-16 text-center">
          <div className="inline-flex flex-col items-center p-8 rounded-2xl border border-dashed border-border-bright">
            <svg className="w-10 h-10 text-text-dim mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 4v16m8-8H4" />
            </svg>
            <p className="text-foreground font-semibold mb-1">Share Your Mod</p>
            <p className="text-sm text-text-muted mb-4">Upload your creation for the community</p>
            <button className="px-5 py-2 rounded-lg text-sm font-medium bg-surface-card border border-border text-text-muted hover:text-foreground hover:border-gold/40 transition-all cursor-pointer">
              Sign in with Discord to upload
            </button>
          </div>
        </div>
      </main>
    </>
  );
}
