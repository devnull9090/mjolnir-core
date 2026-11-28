"use client";

import { useEffect, useState, type ReactNode } from "react";

/**
 * Fixed navbar container that gains crisper depth and border contrast once the
 * reader scrolls past the hero fold.
 */
export function NavbarShell({ children }: { children: ReactNode }) {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const check = () => setScrolled(window.scrollY > 24);
    check();
    window.addEventListener("scroll", check, { passive: true });
    return () => window.removeEventListener("scroll", check);
  }, []);

  return (
    <nav
      aria-label="Main"
      className={`fixed top-0 left-0 right-0 z-50 border-b transition-[background-color,border-color,box-shadow] duration-300 ${
        scrolled
          ? "border-gold/20 bg-background/92 md:backdrop-blur-xl shadow-[0_12px_36px_-18px_rgba(0,0,0,0.9)]"
          : "border-border/50 bg-background md:bg-background/60 md:backdrop-blur-xl"
      }`}
    >
      {children}
    </nav>
  );
}
