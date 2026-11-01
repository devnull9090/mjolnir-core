import type { ReactNode } from "react";

import { Footer } from "../Footer";
import { Navbar } from "../Navbar";

const WIDTHS = {
  xl: "max-w-xl",
  "2xl": "max-w-2xl",
  "3xl": "max-w-3xl",
  "4xl": "max-w-4xl",
  "5xl": "max-w-5xl",
  "6xl": "max-w-6xl",
} as const;

/**
 * The frame every ordinary page sits in: the fixed navbar, a `<main>` that
 * clears it, and the footer. The navbar's height (alpha banner plus bar)
 * lives in one place — here — instead of a `pt-*` pair on every page.
 */
export function PageShell({
  width = "6xl",
  className = "",
  children,
}: {
  width?: keyof typeof WIDTHS;
  className?: string;
  children: ReactNode;
}) {
  return (
    <>
      <Navbar />
      <main id="main" className={`${WIDTHS[width]} mx-auto px-4 sm:px-6 pt-36 pb-20 ${className}`}>
        {children}
      </main>
      <Footer />
    </>
  );
}
