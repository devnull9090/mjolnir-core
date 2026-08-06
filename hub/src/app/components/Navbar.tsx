import Link from "next/link";
import { Download, Construction } from "lucide-react";
import { MobileNav } from "./MobileNav";
import { AuthButton } from "./AuthButton";

function DiscordIcon({ className = "w-5 h-5" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028c.462-.63.874-1.295 1.226-1.994a.076.076 0 0 0-.041-.106 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z" />
    </svg>
  );
}

function GitHubIcon({ className = "w-5 h-5" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12" />
    </svg>
  );
}

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
