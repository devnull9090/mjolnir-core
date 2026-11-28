import type React from "react";
import { invoke } from "@tauri-apps/api/core";
import { openUrl } from "@tauri-apps/plugin-opener";
import type { View } from "../App";
import type { UpdateState } from "./UpdaterBanner";
import { usePreflight } from "../launch/preflight";
import { HUB_SITE } from "../hub/client";

const navItems: { id: View; label: string; icon: React.ReactNode }[] = [
  {
    id: "home",
    label: "Home",
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.6} d="M3 10.5L12 3l9 7.5M5 9.5V20a1 1 0 001 1h4.5v-6h3v6H18a1 1 0 001-1V9.5" />
      </svg>
    ),
  },
  {
    id: "mods",
    label: "My Mods",
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.6} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
      </svg>
    ),
  },
  {
    id: "multiplayer",
    label: "Multiplayer",
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.6} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z" />
      </svg>
    ),
  },
  {
    id: "browse",
    label: "Browse Hub",
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.6} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
      </svg>
    ),
  },
  {
    id: "tools",
    label: "Tools",
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.6} d="M11 4a4 4 0 015.66 5.66l-7 7a4 4 0 01-5.66-5.66M14 7l3 3M4.5 19.5l4-4" />
      </svg>
    ),
  },
  {
    id: "updates",
    label: "Updates",
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.6} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
      </svg>
    ),
  },
  {
    id: "settings",
    label: "Settings",
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.6} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.573-1.066z" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.6} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
      </svg>
    ),
  },
];

interface SidebarProps {
  activeView: View;
  onNavigate: (view: View) => void;
  updater: UpdateState;
  /** Everything out of date, launcher included; badges the Updates item. */
  updateCount: number;
  /** Public lobbies open on the hub right now. */
  liveLobbies?: number;
}

export default function Sidebar({
  activeView,
  onNavigate,
  updater,
  updateCount,
  liveLobbies = 0,
}: SidebarProps) {
  const preflight = usePreflight();
  const showUpdateBadge =
    updater.status === "dismissed" || updater.status === "available" || updater.status === "error";

  return (
    <aside className="w-56 shrink-0 bg-surface-secondary border-r border-border-subtle flex flex-col">
      {/* Logo / Brand */}
      <button
        type="button"
        onClick={() => onNavigate("home")}
        className="group px-4 py-4 border-b border-border-subtle flex items-center gap-3 text-left cursor-pointer hover:bg-surface-hover/30 transition-colors"
      >
        <img
          src="/logo-64.webp"
          alt=""
          width={32}
          height={32}
          className="w-8 h-8 object-contain shrink-0 transition-transform duration-200 group-hover:scale-105"
        />
        <div className="min-w-0">
          <h1 className="text-base font-extrabold tracking-wide leading-tight">
            <span className="text-mjolnir-gold">MJOLNIR</span>
          </h1>
          <p className="text-[10px] font-mono text-text-secondary tracking-[0.18em] uppercase">
            Core Launcher
          </p>
        </div>
      </button>

      {/* Navigation */}
      <nav aria-label="Launcher views" className="flex-1 py-3 px-2.5 space-y-1 overflow-y-auto">
        {navItems.map((item) => {
          const active = activeView === item.id;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => onNavigate(item.id)}
              aria-current={active ? "page" : undefined}
              className={`group relative w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150 cursor-pointer
                ${
                  active
                    ? "bg-mjolnir-gold/14 text-mjolnir-gold shadow-[inset_0_0_0_1px_rgba(212,168,67,0.2)]"
                    : "text-text-secondary hover:bg-surface-hover/80 hover:text-text-primary"
                }`}
            >
              <span
                aria-hidden="true"
                className={`absolute left-0 inset-y-2 w-0.5 rounded-r-full transition-all duration-200 ${
                  active ? "bg-mjolnir-gold opacity-100" : "bg-mjolnir-gold/50 opacity-0 group-hover:opacity-60"
                }`}
              />
              <span className="shrink-0 transition-transform duration-150 group-hover:scale-105">
                {item.icon}
              </span>
              <span className="flex-1 text-left truncate">{item.label}</span>
              {item.id === "multiplayer" && liveLobbies > 0 && (
                <span
                  title={`${liveLobbies} live public game${liveLobbies === 1 ? "" : "s"}`}
                  className="inline-flex items-center gap-1 rounded-full bg-accent-green/15 px-1.5 py-0.5 text-[10px] font-bold text-accent-green tabular-nums"
                >
                  <span className="h-1.5 w-1.5 rounded-full bg-accent-green animate-pulse" />
                  {liveLobbies}
                </span>
              )}
              {/* Keep Updates button text matching /^Updates\s*\d*$/ for remote updater automation. */}
              {item.id === "updates" && updateCount > 0 && (
                <span
                  title={`${updateCount} update${updateCount === 1 ? "" : "s"} available`}
                  className="min-w-5 text-center px-1.5 py-0.5 rounded-full text-[11px] font-bold text-surface-primary bg-mjolnir-gold tabular-nums"
                >
                  {updateCount}
                </span>
              )}
            </button>
          );
        })}
      </nav>

      {/* A launcher update is one row of the Updates view like any other, so
          it is announced by the badge above and the banner — not by a third
          control that acts on its own. */}
      {showUpdateBadge && updater.version && (
        <div className="px-3 mb-2">
          <button
            type="button"
            onClick={() => onNavigate("updates")}
            className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-medium
              bg-mjolnir-gold/10 border border-mjolnir-gold/30
              text-mjolnir-gold hover:bg-mjolnir-gold/20
              transition-all duration-200 cursor-pointer"
          >
            <span className="relative flex h-2.5 w-2.5 shrink-0">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-mjolnir-gold opacity-75" />
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-mjolnir-gold" />
            </span>
            <span className="flex-1 text-left truncate">Launcher v{updater.version} ready</span>
          </button>
        </div>
      )}

      {/* Launch Button */}
      <div className="p-3.5 border-t border-border-subtle">
        <button
          type="button"
          onClick={() =>
            // Updates, a file check and unsupported mods first
            // (launch/PreflightProvider.tsx), then the game.
            preflight.run({ launch: () => invoke("launch_game") }).catch(console.error)
          }
          className="launcher-sheen w-full py-3 rounded-xl font-bold text-sm tracking-wide uppercase
            bg-gradient-to-r from-[#e5bc57] via-mjolnir-gold to-mjolnir-gold-dim
            text-surface-primary
            hover:brightness-110 active:scale-[0.98]
            transition-all duration-150 cursor-pointer
            shadow-lg shadow-mjolnir-gold/25 flex items-center justify-center gap-2"
        >
          <svg className="w-4 h-4 fill-current" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M8 5v14l11-7z" />
          </svg>
          Launch Game
        </button>
      </div>

      {/* Hub & Discord Footer Links */}
      <div className="px-3.5 pb-3.5 grid grid-cols-2 gap-1.5">
        <button
          type="button"
          onClick={() => void openUrl(HUB_SITE)}
          className="flex items-center justify-center gap-1.5 py-2 rounded-lg text-xs text-text-secondary
            hover:text-mjolnir-gold hover:bg-surface-hover transition-all duration-150 cursor-pointer"
          title="Open mjolnircore.com in your browser"
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.7} d="M12 21a9 9 0 100-18 9 9 0 000 18zm0 0c2.5 0 4.5-4.03 4.5-9S14.5 3 12 3m0 18c-2.5 0-4.5-4.03-4.5-9S9.5 3 12 3m-8.5 9h17" />
          </svg>
          Hub Web
        </button>
        <a
          href="https://discord.gg/9gxYZsByW9"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center justify-center gap-1.5 py-2 rounded-lg text-xs text-text-secondary
            hover:text-accent-blue hover:bg-surface-hover transition-all duration-150"
        >
          <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="currentColor">
            <path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028c.462-.63.874-1.295 1.226-1.994a.076.076 0 0 0-.041-.106 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z" />
          </svg>
          Discord
        </a>
      </div>
    </aside>
  );
}
