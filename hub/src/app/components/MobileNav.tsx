"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import {
  Menu,
  X,
  Download,
  KeyRound,
  LogOut,
  Newspaper,
  ScrollText,
  ShieldCheck,
  Wrench,
} from "lucide-react";
import { DiscordIcon, GitHubIcon } from "./icons";
import { useHub } from "./HubKit";

const navLinks = [
  { href: "/docs", label: "Docs" },
  { href: "/mods", label: "Mods" },
  { href: "/tools", label: "Tools", icon: Wrench },
  { href: "/changelog", label: "Changelog", icon: ScrollText },
  { href: "/blog", label: "Blog", icon: Newspaper },
  { href: "/download", label: "Download", icon: Download },
];

const externalLinks = [
  { href: "https://discord.gg/9gxYZsByW9", label: "Discord", icon: DiscordIcon },
  { href: "https://github.com/devnull9090/mjolnir-core", label: "GitHub", icon: GitHubIcon },
];

export function MobileNav() {
  const [open, setOpen] = useState(false);
  const { user, ready, signIn, signOut } = useHub();

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
      {/* Hamburger button — visible only on mobile */}
      <button
        onClick={() => setOpen(true)}
        className="md:hidden p-2 -mr-2 text-text-muted hover:text-foreground transition-colors cursor-pointer"
        aria-label="Open navigation menu"
      >
        <Menu className="w-6 h-6" />
      </button>

      {/* Backdrop */}
      <div
        className={`fixed inset-0 z-[60] bg-black/60 backdrop-blur-sm transition-opacity duration-300 md:hidden ${
          open ? "opacity-100" : "opacity-0 pointer-events-none"
        }`}
        onClick={close}
        aria-hidden="true"
      />

      {/* Drawer panel */}
      <div
        className={`fixed top-0 right-0 z-[70] h-full w-72 max-w-[85vw] bg-surface border-l border-border shadow-2xl transition-all duration-300 ease-out md:hidden flex flex-col ${
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
                  <img src={user.avatar_url} alt="" className="w-8 h-8 rounded-full" />
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

          {navLinks.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              onClick={close}
              className="flex items-center gap-3 px-3 py-3 rounded-lg text-base font-medium text-text-muted hover:text-foreground hover:bg-surface-raised transition-colors"
            >
              {Icon && <Icon className="w-5 h-5" />}
              {label}
            </Link>
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
