import Link from "next/link";
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

/** One figure with its label: a career total, a match length. */
export function StatTile({
  label,
  value,
  hint,
  accent = false,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  accent?: boolean;
}) {
  return (
    <div className={`rounded-xl border px-4 py-3 ${accent ? "border-gold/30 bg-gold/5" : "border-border bg-surface"}`}>
      <dt className="text-[11px] font-semibold uppercase tracking-wider text-text-muted">{label}</dt>
      <dd className={`mt-0.5 text-2xl font-black tabular-nums ${accent ? "text-gold" : "text-foreground"}`}>{value}</dd>
      {hint && <dd className="text-xs text-text-muted">{hint}</dd>}
    </div>
  );
}

/** A row of stat tiles as one description list. */
export function StatGrid({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <dl className={`grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 ${className}`}>{children}</dl>;
}

/** What an empty list says instead: what would be here, and how to make some. */
export function EmptyState({
  icon: Icon,
  title,
  children,
  action,
}: {
  icon: LucideIcon;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center rounded-2xl border border-dashed border-border-bright bg-surface/40 px-6 py-14 text-center">
      <span className="mb-4 inline-flex h-12 w-12 items-center justify-center rounded-full bg-gold/10 text-gold">
        <Icon aria-hidden className="h-6 w-6" />
      </span>
      <p className="text-lg font-bold text-foreground">{title}</p>
      {children && <div className="mt-1 max-w-md text-sm text-text-muted">{children}</div>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

/** Newest / Older for a list paged by a cursor. */
export function Pager({ newest, older }: { newest?: string; older?: string }) {
  if (!newest && !older) return null;
  const cls =
    "inline-flex min-h-10 items-center rounded-lg border border-border px-4 text-sm font-semibold transition-colors";
  return (
    <nav aria-label="Pages" className="mt-8 flex items-center justify-between gap-4">
      {newest ? (
        <Link href={newest} className={`${cls} text-text-muted hover:text-foreground hover:border-border-bright`}>
          ← Newest
        </Link>
      ) : (
        <span />
      )}
      {older && (
        <Link href={older} className={`${cls} border-gold/40 text-gold hover:bg-gold/10`}>
          Older →
        </Link>
      )}
    </nav>
  );
}

/** A small label for a fact about a thing: a game type, a state. */
export function Pill({
  tone = "neutral",
  children,
  className = "",
}: {
  tone?: "neutral" | "gold" | "green" | "red" | "blue" | "solid";
  children: ReactNode;
  className?: string;
}) {
  const tones = {
    neutral: "border-border-bright bg-surface-raised/80 text-text-muted",
    gold: "border-gold/40 bg-gold/15 text-gold",
    green: "border-accent-green/40 bg-accent-green/15 text-accent-green",
    red: "border-team-red/40 bg-team-red/15 text-team-red",
    blue: "border-team-blue/40 bg-team-blue/15 text-team-blue",
    // Over an image: opaque enough to read on any screenshot.
    solid: "border-white/10 bg-background/80 text-foreground backdrop-blur-sm",
  };
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${tones[tone]} ${className}`}
    >
      {children}
    </span>
  );
}

/**
 * The frame a data table sits in: rounded, bordered, and scrolling sideways
 * on a phone. `relative` matters: without it, `sr-only` text in the table
 * (absolutely positioned) escapes the scroller and widens the whole page.
 */
export function TableFrame({ children }: { children: ReactNode }) {
  return <div className="relative overflow-x-auto rounded-xl border border-border bg-surface">{children}</div>;
}
