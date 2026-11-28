"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Blocks,
  BookOpen,
  Download,
  Gamepad2,
  KeyRound,
  LogOut,
  Map as MapIcon,
  Menu,
  Newspaper,
  Package,
  Radio,
  ScrollText,
  ShieldCheck,
  Swords,
  Trophy,
  UserRound,
  Wrench,
  X,
} from "lucide-react";
import { DiscordIcon, GitHubIcon } from "./icons";
import { useHub } from "./HubKit";
import { isActive } from "./nav";

const navSections = [
  {
    heading: "Play",
    links: [
      { href: "/multiplayer", label: "Multiplayer", icon: Gamepad2 },
      { href: "/games", label: "Live Games", icon: Radio },
      { href: "/matches", label: "Matches", icon: Swords },
      { href: "/leaderboards", label: "Players", icon: Trophy },
    ],
  },
  {
    heading: "Workshop",
    links: [
      { href: "/maps", label: "Maps", icon: MapIcon },
      { href: "/mods", label: "Mods", icon: Package },
      { href: "/forge", label: "Forge Packs", icon: Blocks },
    ],
  },
  {
    heading: "Create & News",
    links: [
      { href: "/docs", label: "Docs", icon: BookOpen },
      { href: "/tools", label: "Tools", icon: Wrench },
      { href: "/blog", label: "Blog", icon: Newspaper },
      { href: "/changelog", label: "Changelog", icon: ScrollText },
    ],
  },
];

const externalLinks = [
  { href: "https://discord.gg/9gxYZsByW9", label: "Discord", icon: DiscordIcon },
  { href: "https://github.com/devnull9090/mjolnir-core", label: "GitHub", icon: GitHubIcon },
];

export function MobileNav() {
  const [open, setOpen] = useState(false);
  const { user, ready, signIn, signOut } = useHub();
  const pathname = usePathname() ?? "/";

  const close = useCallback(() => setOpen(false), []);

  // Lock body scroll when drawer is open
  useEffect(() => {
    if (open) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  // Close on Escape
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") close();
    }
    if (open) {
      document.addEventListener("keydown", onKeyDown);
      return () => document.removeEventListener("keydown", onKeyDown);
    }
  }, [open, close]);

  return (
    <>
      {/* Hamburger button — below lg, where the desktop row does not fit */}
      <button
        onClick={() => setOpen(true)}
        aria-expanded={open}
        className="lg:hidden p-2 -mr-2 text-text-muted hover:text-foreground transition-colors cursor-pointer"
        aria-label="Open navigation menu"
      >
        <Menu className="w-6 h-6" />
      </button>

      {/* Backdrop */}
      <div
        className={`fixed inset-0 z-[60] bg-black/60 backdrop-blur-sm transition-opacity duration-300 lg:hidden ${
          open ? "opacity-100" : "opacity-0 pointer-events-none"
        }`}
        onClick={close}
        aria-hidden="true"
      />

      {/* Drawer panel */}
      <div
        className={`fixed top-0 right-0 z-[70] h-full w-72 max-w-[85vw] bg-surface border-l border-border shadow-2xl transition-all duration-300 ease-out lg:hidden flex flex-col ${
          open ? "translate-x-0 opacity-100" : "translate-x-full opacity-0 invisible pointer-events-none"
        }`}
        role="dialog"
        aria-modal="true"
        aria-label="Navigation menu"
      >
        {/* Close button */}
        <div className="flex items-center justify-between px-5 h-16 border-b border-border shrink-0">
          <span className="text-sm font-bold text-gold uppercase tracking-wider">Menu</span>
          <button
            onClick={close}
            className="p-2 -mr-2 text-text-muted hover:text-foreground transition-colors cursor-pointer"
            aria-label="Close navigation menu"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Links */}
        <nav className="px-5 py-6 space-y-1 flex-1 overflow-y-auto">
          {/* Account — same shared session the desktop chip reads. */}
          {ready && !user && (
            <button
              onClick={signIn}
              className="flex items-center gap-3 w-full px-3 py-3 rounded-lg text-base font-medium border border-[#5865F2]/60 text-[#8b95f6] hover:bg-[#5865F2]/10 transition-colors cursor-pointer"
            >
              <DiscordIcon className="w-5 h-5" />
              Sign in with Discord
            </button>
          )}
          {user && (
            <>
              <Link
                href={`/users/${user.id}`}
                onClick={close}
                className="flex items-center gap-3 px-3 py-3 rounded-lg hover:bg-surface-raised transition-colors"
              >
                {user.avatar_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={user.avatar_url} alt="" crossOrigin="anonymous" className="w-8 h-8 rounded-full" />
                ) : (
                  <div className="w-8 h-8 rounded-full bg-surface-raised" />
                )}
                <span className="flex-1 min-w-0 text-base font-medium text-foreground truncate">
                  {user.display_name ?? user.username}
                </span>
                {user.role !== "user" && (
                  <span className="px-1.5 py-0.5 rounded text-[10px] font-bold uppercase bg-gold/15 text-gold">
                    {user.role}
                  </span>
                )}
              </Link>
              {user.role !== "user" && (
                <Link
                  href="/moderation"
                  onClick={close}
                  className="flex items-center gap-3 px-3 py-3 rounded-lg text-base font-medium text-gold hover:brightness-110 hover:bg-surface-raised transition-colors"
                >
                  <ShieldCheck className="w-5 h-5" />
                  Moderation
                </Link>
              )}
              <Link
                href="/account"
                onClick={close}
                className="flex items-center gap-3 px-3 py-3 rounded-lg text-base font-medium text-text-muted hover:text-foreground hover:bg-surface-raised transition-colors"
              >
                <UserRound className="w-5 h-5" />
                Account
              </Link>
              <Link
                href="/account/keys"
                onClick={close}
                className="flex items-center gap-3 px-3 py-3 rounded-lg text-base font-medium text-text-muted hover:text-foreground hover:bg-surface-raised transition-colors"
              >
                <KeyRound className="w-5 h-5" />
                API keys
              </Link>
              <button
                onClick={() => {
                  signOut();
                  close();
                }}
                className="flex items-center gap-3 w-full px-3 py-3 rounded-lg text-base font-medium text-text-muted hover:text-foreground hover:bg-surface-raised transition-colors cursor-pointer"
              >
                <LogOut className="w-5 h-5" />
                Sign out
              </button>
            </>
          )}
          {ready && <div className="border-t border-border my-4" />}

          {navSections.map((section, sIdx) => (
            <div key={section.heading} className={sIdx > 0 ? "pt-3" : undefined}>
              <p className="px-3 pb-1.5 font-mono text-[10px] font-semibold uppercase tracking-[0.16em] text-text-dim">
                {section.heading}
              </p>
              {section.links.map(({ href, label, icon: Icon }) => {
                const active = isActive(href, pathname);
                return (
                  <Link
                    key={href}
                    href={href}
                    onClick={close}
                    aria-current={active ? "page" : undefined}
                    className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-base font-medium transition-colors ${
                      active
                        ? "bg-gold/10 text-gold"
                        : "text-text-muted hover:text-foreground hover:bg-surface-raised"
                    }`}
                  >
                    <Icon aria-hidden className="w-5 h-5" />
                    {label}
                  </Link>
                );
              })}
            </div>
          ))}

          <div className="border-t border-border my-4" />

          {externalLinks.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              target="_blank"
              onClick={close}
              className="flex items-center gap-3 px-3 py-3 rounded-lg text-base font-medium text-text-muted hover:text-foreground hover:bg-surface-raised transition-colors"
            >
              <Icon className="w-5 h-5" />
              {label}
            </Link>
          ))}
        </nav>

        {/* Download CTA at bottom */}
        <div className="p-5 border-t border-border bg-surface shrink-0">
          <Link
            href="/download"
            onClick={close}
            className="flex items-center justify-center gap-2 w-full px-4 py-3 rounded-xl font-bold text-sm bg-gradient-to-r from-gold to-gold-dim text-background hover:brightness-110 transition-all shadow-lg shadow-gold/20"
          >
            <Download className="w-4 h-4" />
            Download Launcher
          </Link>
        </div>
      </div>
    </>
  );
}
