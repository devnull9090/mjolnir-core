"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { DESKTOP_NAV, isActive } from "./nav";

/** The desktop bar's section links, with the current section marked. */
export function NavLinks() {
  const pathname = usePathname() ?? "/";
  return (
    <ul className="flex items-center gap-1 xl:gap-2">
      {DESKTOP_NAV.map(({ href, label }) => {
        const active = isActive(href, pathname);
        return (
          <li key={href}>
            <Link
              href={href}
              aria-current={active ? "page" : undefined}
              className={`relative rounded-md px-2 py-2 text-sm transition-colors after:absolute after:inset-x-2 after:-bottom-[13px] after:h-0.5 after:rounded-full after:transition-colors ${
                active
                  ? "text-foreground font-semibold after:bg-gold"
                  : "text-text-muted hover:text-foreground after:bg-transparent"
              }`}
            >
              {label}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
