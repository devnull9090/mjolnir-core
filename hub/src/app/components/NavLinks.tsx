"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Blocks,
  BookOpen,
  ChevronDown,
  Gamepad2,
  Map as MapIcon,
  Newspaper,
  Package,
  Radio,
  ScrollText,
  Swords,
  Trophy,
  Wrench,
} from "lucide-react";

import { DESKTOP_NAV, isActive, isGroupActive, type NavIconKey } from "./nav";

const ICONS: Record<NavIconKey, typeof Gamepad2> = {
  gamepad: Gamepad2,
  radio: Radio,
  swords: Swords,
  trophy: Trophy,
  map: MapIcon,
  package: Package,
  book: BookOpen,
  wrench: Wrench,
  blocks: Blocks,
  scroll: ScrollText,
  newspaper: Newspaper,
};

/**
 * Desktop navigation bar with 5 clean top-level slots (two lightweight
 * dropdown menus + three direct links) so the header stays uncrowded at every
 * viewport width.
 */
export function NavLinks() {
  const pathname = usePathname() ?? "/";
  const [openId, setOpenId] = useState<string | null>(null);
  const navRef = useRef<HTMLElement>(null);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const openedByHover = useRef<string | null>(null);

  const clearCloseTimer = () => {
    if (closeTimer.current) {
      clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
  };

  const scheduleClose = () => {
    clearCloseTimer();
    closeTimer.current = setTimeout(() => {
      openedByHover.current = null;
      setOpenId(null);
    }, 130);
  };

  // Close on click outside or Escape
  useEffect(() => {
    if (!openId) return;
    const onPointerDown = (e: PointerEvent) => {
      if (navRef.current && !navRef.current.contains(e.target as Node)) {
        setOpenId(null);
      }
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpenId(null);
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [openId]);

  useEffect(() => () => clearCloseTimer(), []);

  return (
    <nav ref={navRef} aria-label="Main navigation">
      <ul className="flex items-center gap-1 xl:gap-1.5">
        {DESKTOP_NAV.map((entry) => {
          if (entry.kind === "link") {
            const active = isActive(entry.href, pathname);
            return (
              <li key={entry.href}>
                <Link
                  href={entry.href}
                  aria-current={active ? "page" : undefined}
                  onClick={() => setOpenId(null)}
                  className={`relative inline-flex items-center rounded-md px-3 py-2 text-sm transition-colors after:absolute after:inset-x-3 after:-bottom-[13px] after:h-0.5 after:rounded-full after:transition-colors ${
                    active
                      ? "font-semibold text-foreground after:bg-gold"
                      : "text-text-muted hover:text-foreground after:bg-transparent"
                  }`}
                >
                  {entry.label}
                </Link>
              </li>
            );
          }

          const isOpen = openId === entry.id;
          const active = isGroupActive(entry.items, pathname);

          return (
            <li
              key={entry.id}
              className="relative"
              onMouseEnter={() => {
                clearCloseTimer();
                if (openId !== entry.id) {
                  openedByHover.current = entry.id;
                  setOpenId(entry.id);
                }
              }}
              onMouseLeave={scheduleClose}
            >
              <button
                type="button"
                aria-expanded={isOpen}
                aria-haspopup="menu"
                onClick={() => {
                  clearCloseTimer();
                  if (openId === entry.id && openedByHover.current === entry.id) {
                    // Hover just opened it; clicking pins it open instead of slamming it shut.
                    openedByHover.current = null;
                    return;
                  }
                  openedByHover.current = null;
                  setOpenId((prev) => (prev === entry.id ? null : entry.id));
                }}
                className={`relative inline-flex items-center gap-1.5 rounded-md px-3 py-2 text-sm transition-colors cursor-pointer after:absolute after:inset-x-3 after:-bottom-[13px] after:h-0.5 after:rounded-full after:transition-colors ${
                  active || isOpen
                    ? "font-semibold text-foreground"
                    : "text-text-muted hover:text-foreground"
                } ${active ? "after:bg-gold" : "after:bg-transparent"}`}
              >
                <span>{entry.label}</span>
                <ChevronDown
                  aria-hidden="true"
                  className={`size-3.5 text-text-dim transition-transform duration-150 ${
                    isOpen ? "rotate-180 text-gold" : ""
                  }`}
                />
              </button>

              {isOpen && (
                <div
                  role="menu"
                  aria-label={entry.label}
                  onMouseEnter={clearCloseTimer}
                  onMouseLeave={scheduleClose}
                  className="mj-select-menu absolute left-0 top-full z-50 mt-2.5 w-72 rounded-xl border border-border-bright bg-surface/95 p-1.5 shadow-[0_20px_48px_-12px_rgba(0,0,0,0.8)] backdrop-blur-xl"
                >
                  {entry.items.map((item) => {
                    const Icon = ICONS[item.icon];
                    const itemActive = isActive(item.href, pathname);
                    return (
                      <Link
                        key={item.href}
                        href={item.href}
                        role="menuitem"
                        aria-current={itemActive ? "page" : undefined}
                        onClick={() => setOpenId(null)}
                        className={`group flex items-start gap-3 rounded-lg px-3 py-2.5 transition-colors ${
                          itemActive
                            ? "bg-gold/10 text-foreground"
                            : "text-text-muted hover:bg-surface-raised hover:text-foreground"
                        }`}
                      >
                        <span
                          className={`mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg border transition-colors ${
                            itemActive
                              ? "border-gold/40 bg-gold/15 text-gold"
                              : "border-border bg-background/70 text-text-muted group-hover:border-border-bright group-hover:text-gold"
                          }`}
                        >
                          <Icon aria-hidden="true" className="size-4" />
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="flex items-center gap-2 text-sm font-semibold leading-5 text-foreground">
                            {item.label}
                            {itemActive && (
                              <span className="size-1.5 rounded-full bg-gold" aria-hidden="true" />
                            )}
                          </span>
                          <span className="mt-0.5 block text-xs leading-4 text-text-dim">
                            {item.description}
                          </span>
                        </span>
                      </Link>
                    );
                  })}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
