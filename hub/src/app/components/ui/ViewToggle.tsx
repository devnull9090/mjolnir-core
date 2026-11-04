import Link from "next/link";
import { LayoutGrid, List } from "lucide-react";

/**
 * Grid or table, as two links. The view lives in the URL so a shared link
 * opens the same way and the server renders it with no flash.
 */
export function ViewToggle({ view, gridHref, tableHref }: { view: "grid" | "table"; gridHref: string; tableHref: string }) {
  const item = (active: boolean) =>
    `inline-flex min-h-9 items-center gap-1.5 rounded-md px-3 text-sm transition-colors ${
      active ? "bg-surface-hover text-foreground font-semibold" : "text-text-muted hover:text-foreground"
    }`;
  return (
    <nav aria-label="View" className="inline-flex rounded-lg border border-border bg-surface p-1">
      <Link href={gridHref} aria-current={view === "grid" ? "page" : undefined} className={item(view === "grid")} scroll={false}>
        <LayoutGrid aria-hidden className="h-4 w-4" />
        Cards
      </Link>
      <Link href={tableHref} aria-current={view === "table" ? "page" : undefined} className={item(view === "table")} scroll={false}>
        <List aria-hidden className="h-4 w-4" />
        Table
      </Link>
    </nav>
  );
}
