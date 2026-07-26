import type React from "react";
import { invoke } from "@tauri-apps/api/core";
import type { View } from "../App";
import type { UpdateState } from "./UpdaterBanner";

const navItems: { id: View; label: string; icon: React.ReactNode }[] = [
  {
    id: "mods",
    label: "My Mods",
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
      </svg>
    ),
  },
  {
    id: "browse",
    label: "Browse Hub",
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
      </svg>
    ),
  },
  {
    id: "settings",
    label: "Settings",
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.573-1.066z" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
      </svg>
    ),
  },
];

interface SidebarProps {
  activeView: View;
  onNavigate: (view: View) => void;
  updater: UpdateState;
}

export default function Sidebar({ activeView, onNavigate, updater }: SidebarProps) {
  const showUpdateBadge = updater.status === "dismissed" || updater.status === "available" || updater.status === "error";

  return (
    <aside className="w-56 bg-surface-secondary border-r border-border-subtle flex flex-col">
      {/* Logo / Brand */}
      <div className="px-5 py-5 border-b border-border-subtle">
        <h1 className="text-lg font-bold tracking-wide">
          <span className="text-mjolnir-gold">MJOLNIR</span>
        </h1>
        <p className="text-[11px] text-text-secondary mt-0.5 tracking-widest uppercase">
          Mod Launcher
        </p>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-3 px-3 space-y-1">
        {navItems.map((item) => (
          <button
            key={item.id}
            onClick={() => onNavigate(item.id)}
            className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150 cursor-pointer
              ${
                activeView === item.id
                  ? "bg-mjolnir-gold/15 text-mjolnir-gold"
                  : "text-text-secondary hover:bg-surface-hover hover:text-text-primary"
              }`}
          >
            {item.icon}
            {item.label}
          </button>
        ))}
      </nav>

      {/* Update Available Badge */}
      {showUpdateBadge && updater.version && (
        <div className="px-3 mb-2">
          <button
            onClick={async () => {
              if (updater.status === "dismissed") {
                // Re-show the banner
                await updater.recheck();
              } else {
                await updater.handleInstall();
              }
            }}
            className="w-full flex items-center gap-2 px-3 py-2.5 rounded-lg text-xs font-medium
              bg-mjolnir-gold/10 border border-mjolnir-gold/30
              text-mjolnir-gold hover:bg-mjolnir-gold/20
              transition-all duration-200 cursor-pointer group"
          >
            <span className="relative flex h-2.5 w-2.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-mjolnir-gold opacity-75" />
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-mjolnir-gold" />
            </span>
            <span className="flex-1 text-left">
              v{updater.version} available
            </span>
            <svg className="w-3.5 h-3.5 opacity-50 group-hover:opacity-100 transition-opacity" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
          </button>
        </div>
      )}

      {/* Launch Button */}
      <div className="p-4 border-t border-border-subtle">
        <button
          onClick={() => invoke("launch_game").catch(console.error)}
          className="w-full py-3 rounded-lg font-bold text-sm tracking-wide uppercase
            bg-gradient-to-r from-mjolnir-gold to-mjolnir-gold-dim
            text-surface-primary
            hover:brightness-110 active:brightness-90
            transition-all duration-150 cursor-pointer
            shadow-lg shadow-mjolnir-gold/20"
        >
          ▶ Launch Game
        </button>
      </div>

      {/* Discord Link */}
      <div className="px-4 pb-4">
        <a
          href="https://discord.gg/9gxYZsByW9"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center justify-center gap-2 py-2 rounded-lg text-xs text-text-secondary
            hover:text-accent-blue hover:bg-surface-hover transition-all duration-150"
        >
          <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
            <path d="M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58.099 18.057a.082.082 0 0 0 .031.057 19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028c.462-.63.874-1.295 1.226-1.994a.076.076 0 0 0-.041-.106 13.107 13.107 0 0 1-1.872-.892.077.077 0 0 1-.008-.128 10.2 10.2 0 0 0 .372-.292.074.074 0 0 1 .077-.01c3.928 1.793 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006.127 12.299 12.299 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03zM8.02 15.33c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.956-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.956 2.418-2.157 2.418zm7.975 0c-1.183 0-2.157-1.085-2.157-2.419 0-1.333.955-2.419 2.157-2.419 1.21 0 2.176 1.096 2.157 2.42 0 1.333-.946 2.418-2.157 2.418z" />
          </svg>
          Join Discord
        </a>
      </div>
    </aside>
  );
}
