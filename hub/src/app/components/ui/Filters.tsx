import Link from "next/link";
import type { ReactNode } from "react";

import { SelectNav } from "./SelectNav";

export interface FilterOption {
  label: ReactNode;
  href: string;
  active: boolean;
}

const CHIP =
  "inline-flex min-h-9 items-center gap-1.5 whitespace-nowrap rounded-full border px-3.5 text-sm transition-colors";
const CHIP_ON = "border-gold/60 bg-gold/10 text-gold font-semibold";
const CHIP_OFF = "border-border bg-surface/60 text-text-muted hover:border-border-bright hover:text-foreground";

/**
 * One filter as a row of links. Server-rendered (each chip is a URL), so it
 * works before hydration and the back button undoes it. On a phone the row
 * scrolls sideways instead of wrapping into a wall of chips.
 */
export function FilterChips({ label, options }: { label: string; options: FilterOption[] }) {
  return (
    <nav aria-label={label} className="relative -mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0 [scrollbar-width:none]">
      <ul className="flex w-max gap-2 sm:w-auto sm:flex-wrap">
        {options.map((o) => (
          <li key={o.href}>
            <Link
              href={o.href}
              aria-current={o.active ? "page" : undefined}
              className={`${CHIP} ${o.active ? CHIP_ON : CHIP_OFF}`}
            >
              {o.label}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}

/** A lone on/off filter that sits with the chips. */
export function ToggleChip({ href, active, children }: { href: string; active: boolean; children: ReactNode }) {
  return (
    <Link href={href} className={`${CHIP} ${active ? CHIP_ON : CHIP_OFF}`}>
      {children}
      <span className="sr-only">{active ? " (on)" : " (off)"}</span>
    </Link>
  );
}

/**
 * The bar of filters above a list: chips for the few-choice filters, and a
 * select for the many-choice one (forty maps do not belong in chips).
 */
export function FilterBar({ children }: { children: ReactNode }) {
  return (
    <div className="mb-6 flex flex-col gap-3 rounded-2xl border border-border bg-surface/50 p-3 sm:p-4">
      {children}
    </div>
  );
}

export { SelectNav };
