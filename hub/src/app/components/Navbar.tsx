import Link from "next/link";
import { Logo } from "./Logo";
import { Download } from "lucide-react";
import { MobileNav } from "./MobileNav";
import { AuthButton } from "./AuthButton";
import { DiscordIcon, GitHubIcon } from "./icons";
import { NavLinks } from "./NavLinks";
import { NavbarShell } from "./NavbarShell";

/* ── Alpha Banner ────────────────────────────────────────────────────── */

export function AlphaBanner() {
  return (
    <div className="bg-gradient-to-r from-gold/12 via-gold/5 to-gold/12 border-b border-gold/20">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 py-2 flex flex-wrap items-center justify-center gap-x-2 gap-y-1 text-sm text-center">
        <span className="relative flex size-2 items-center justify-center" aria-hidden="true">
          <span className="mj-live-ring absolute inline-flex size-full rounded-full bg-gold/75" />
          <span className="relative inline-flex size-1.5 rounded-full bg-gold" />
        </span>
        <span className="font-mono text-[11px] uppercase tracking-[0.16em] text-gold font-semibold">Alpha</span>
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
    <NavbarShell>
      <AlphaBanner />
      <div className="max-w-6xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
        <Link href="/" aria-label="MJOLNIR Core home" className="group flex items-center gap-3 shrink-0">
          <Logo className="w-8 h-8 transition-transform duration-200 group-hover:scale-105 motion-reduce:transition-none" />
          <span className="text-lg font-bold tracking-wide text-gold">MJOLNIR</span>
          <span className="text-xs text-text-muted font-medium">CORE</span>
        </Link>

        {/* Changelog stays in the mobile menu and footer to leave room for
            the multiplayer landing page at desktop widths. */}
        <div className="hidden lg:flex items-center gap-3 xl:gap-4">
          <NavLinks />
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
            className="mj-sheen px-3.5 xl:px-4 py-2 text-sm font-semibold rounded-lg bg-gradient-to-r from-gold to-[#c49635] text-background hover:brightness-110 active:scale-[0.98] transition-all shadow-md shadow-gold/15 flex items-center gap-2 whitespace-nowrap"
          >
            <Download className="w-4 h-4" />
            Download
          </Link>
          <AuthButton />
        </div>

        {/* Mobile hamburger */}
        <MobileNav />
      </div>
    </NavbarShell>
  );
}
