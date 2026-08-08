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
          MJOLNIR Core is under active development.
        </span>
        <Link
          href="https://discord.gg/9gxYZsByW9"
          target="_blank"
          className="hidden sm:inline text-gold hover:underline font-medium"
        >
          Join the alpha →
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
        <Link href="/" className="flex items-center gap-3">
          <MjolnirIcon />
          <span className="text-lg font-bold tracking-wide text-gold">MJOLNIR</span>
          <span className="text-xs text-text-muted font-medium">CORE</span>
        </Link>

        {/* Desktop links */}
        <div className="hidden md:flex items-center gap-6 lg:gap-8">
          <Link href="/docs" className="text-sm text-text-muted hover:text-foreground transition-colors">
            Docs
          </Link>
          <Link href="/mods" className="text-sm text-text-muted hover:text-foreground transition-colors">
            Mods
          </Link>
          <Link href="/tools" className="text-sm text-text-muted hover:text-foreground transition-colors">
            Tools
          </Link>
          <Link href="/changelog" className="text-sm text-text-muted hover:text-foreground transition-colors">
            Changelog
          </Link>
          {/* Both held back until lg: with Tools in the row there is no space
              for them at md, and both are still one tap away in the footer. */}
          <Link href="https://discord.gg/9gxYZsByW9" target="_blank" className="hidden lg:flex text-sm text-text-muted hover:text-foreground transition-colors items-center gap-1.5">
            <DiscordIcon className="w-4 h-4" />
            Discord
          </Link>
          <Link href="https://github.com/devnull9090/mjolnir-core" target="_blank" className="hidden lg:flex text-sm text-text-muted hover:text-foreground transition-colors items-center gap-1.5">
            <GitHubIcon className="w-4 h-4" />
            GitHub
          </Link>
          <Link
            href="/download"
            className="px-4 py-2 text-sm font-semibold rounded-lg bg-gold text-background hover:brightness-110 transition-all flex items-center gap-2"
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
