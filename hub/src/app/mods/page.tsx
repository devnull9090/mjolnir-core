import Link from "next/link";
import {
  Download,
  Plus,
  MoreVertical,
} from "lucide-react";
import { Navbar } from "../components/Navbar";
import { Footer } from "../components/Footer";

function DiscordIcon({ className = "w-5 h-5" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028c.462-.63.874-1.295 1.226-1.994a.076.076 0 0 0-.041-.106 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z" />
    </svg>
  );
}

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
    description: "Experimental campaign map travel, listen-server loading, and player admin commands.",
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
      <Navbar />

      <main className="pt-32 md:pt-36 pb-16 px-6 max-w-6xl mx-auto">
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
                    <Download className="w-3 h-3" />
                    {mod.downloads}
                  </span>
                </div>
                <div className="flex items-center gap-1">
                  <button className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-gold/10 text-gold hover:bg-gold/20 transition-colors cursor-pointer flex items-center gap-1">
                    <Download className="w-3 h-3" />
                    Download
                  </button>
                  <button className="p-1.5 rounded-lg text-text-dim hover:text-foreground hover:bg-surface-card transition-colors cursor-pointer opacity-100 md:opacity-0 md:group-hover:opacity-100">
                    <MoreVertical className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Upload CTA */}
        <div className="mt-16 text-center">
          <div className="inline-flex flex-col items-center p-8 rounded-2xl border border-dashed border-border-bright">
            <Plus className="w-10 h-10 text-text-dim mb-3" />
            <p className="text-foreground font-semibold mb-1">Share Your Mod</p>
            <p className="text-sm text-text-muted mb-4">Upload your creation for the community</p>
            <button className="px-5 py-2 rounded-lg text-sm font-medium bg-surface-card border border-border text-text-muted hover:text-foreground hover:border-gold/40 transition-all cursor-pointer flex items-center gap-2">
              <DiscordIcon className="w-4 h-4" />
              Sign in with Discord to upload
            </button>
          </div>
        </div>
      </main>

      <Footer />
    </>
  );
}
