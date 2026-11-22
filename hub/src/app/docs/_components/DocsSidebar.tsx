"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronRight } from "lucide-react";

export type SidebarSection = {
  id: string;
  title: string;
  /** The section's own index page. */
  href: string;
  links: Array<{ href: string; label: string }>;
};

/**
 * The docs' sections, each folded to its title except the one being read.
 * There are some eighty docs: a flat list of them pushed everything after the
 * guides off the screen, which is how the notes went unread.
 */
export function DocsSidebar({ sections }: { sections: SidebarSection[] }) {
  const pathname = usePathname();
  return (
    <div className="space-y-1">
      {sections.map((section, at) => {
        const reading = section.links.some((link) => link.href === pathname);
        return (
          // The key carries `reading` so that arriving in a section opens it
          // even after the reader folded it by hand.
          <details key={`${section.id}-${reading}`} open={reading || (at === 0 && pathname === "/docs")} className="group/section">
            <summary className="flex cursor-pointer list-none items-center gap-2 py-2 text-xs font-bold uppercase text-text-dim hover:text-foreground [&::-webkit-details-marker]:hidden">
              <ChevronRight className="h-3.5 w-3.5 shrink-0 transition-transform group-open/section:rotate-90" aria-hidden />
              <span className="min-w-0 flex-1">{section.title}</span>
              <span className="font-mono text-[10px] font-normal">{section.links.length}</span>
            </summary>
            <div className="mb-3 ml-1.5 space-y-0.5 border-l border-border pl-3">
              {section.links.map(({ href, label }) => {
                const active = href === pathname;
                return (
                  <Link
                    key={href}
                    href={href}
                    aria-current={active ? "page" : undefined}
                    className={`block py-1.5 text-sm leading-5 ${
                      active ? "font-semibold text-gold" : "text-text-muted hover:text-foreground"
                    }`}
                  >
                    {label}
                  </Link>
                );
              })}
            </div>
          </details>
        );
      })}
    </div>
  );
}
