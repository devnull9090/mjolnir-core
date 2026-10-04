import Link from "next/link";
import { Download, Construction } from "lucide-react";
import { MobileNav } from "./MobileNav";
import { AuthButton } from "./AuthButton";
import { DiscordIcon, GitHubIcon } from "./icons";

function MjolnirIcon({ className = "w-8 h-8" }: { className?: string }) {
  return (
    <img
      src="/logo-transparent.png"
      alt="MJOLNIR Core"
      className={`${className} object-contain`}
    />
  );
}

/* ── Alpha Banner ────────────────────────────────────────────────────── */

export function AlphaBanner() {
  return (
    <div className="bg-gradient-to-r from-gold/10 via-gold/5 to-gold/10 border-b border-gold/20">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 py-2 flex flex-wrap items-center justify-center gap-x-2 gap-y-1 text-sm text-center">
        <Construction className="w-4 h-4 text-gold" />
        <span className="text-gold font-semibold">Alpha</span>
        <span className="text-text-muted hidden sm:inline">—</span>
        <span className="text-text-muted">
          Classic Halo multiplayer is here.
        </span>
        <Link
          href="/multiplayer"
          className="text-gold hover:underline font-medium"
        >
          Play the alpha →
        </Link>
      </div>
    </div>
  );
}

/* ── Navbar ───────────────────────────────────────────────────────────── */

export function Navbar() {
  return (
    <nav className="fixed top-0 left-0 right-0 z-50 border-b border-border/50 bg-background md:bg-background/60 md:backdrop-blur-xl">
      <AlphaBanner />
      <div className="max-w-6xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-3 shrink-0">
          <MjolnirIcon />
          <span className="text-lg font-bold tracking-wide text-gold">MJOLNIR</span>
          <span className="text-xs text-text-muted font-medium">CORE</span>
        </Link>

        {/* Changelog stays in the mobile menu and footer to leave room for
            the multiplayer landing page at desktop widths. */}
        <div className="hidden lg:flex items-center gap-4 xl:gap-5">
          <Link href="/multiplayer" className="text-sm text-gold hover:text-foreground transition-colors">
            Multiplayer
          </Link>
          <Link href="/mods" className="text-sm text-text-muted hover:text-foreground transition-colors">
            Mods
          </Link>
          <Link href="/maps" className="text-sm text-text-muted hover:text-foreground transition-colors">
            Maps
          </Link>
          <Link href="/games" className="text-sm text-text-muted hover:text-foreground transition-colors">
            Games
          </Link>
          <Link href="/matches" className="text-sm text-text-muted hover:text-foreground transition-colors">
            Matches
          </Link>
          <Link href="/tools" className="text-sm text-text-muted hover:text-foreground transition-colors">
            Tools
          </Link>
          <Link href="/docs" className="text-sm text-text-muted hover:text-foreground transition-colors">
            Docs
          </Link>
          <Link href="/blog" className="text-sm text-text-muted hover:text-foreground transition-colors">
            Blog
          </Link>
          <Link
            href="https://discord.gg/9gxYZsByW9"
            target="_blank"
            title="Discord"
            aria-label="Discord"
            className="p-1 text-text-muted hover:text-foreground transition-colors"
          >
            <DiscordIcon className="w-5 h-5" />
          </Link>
          <Link
            href="https://github.com/devnull9090/mjolnir-core"
            target="_blank"
            title="GitHub"
            aria-label="GitHub"
            className="p-1 -ml-2 text-text-muted hover:text-foreground transition-colors"
          >
            <GitHubIcon className="w-5 h-5" />
          </Link>
          <Link
            href="/download"
            className="px-3 xl:px-4 py-2 text-sm font-semibold rounded-lg bg-gold text-background hover:brightness-110 transition-all flex items-center gap-2 whitespace-nowrap"
          >
            <Download className="w-4 h-4" />
            Download
          </Link>
          <AuthButton />
        </div>

        {/* Mobile hamburger */}
        <MobileNav />
      </div>
    </nav>
  );
}
