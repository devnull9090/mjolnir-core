import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import type { ReactNode } from "react";

/**
 * A page's title block: an optional way back, an eyebrow, the one `<h1>`,
 * a lede, and actions that sit beside the title on wide screens and under
 * it on a phone.
 */
export function PageHeader({
  title,
  eyebrow,
  description,
  back,
  actions,
  children,
}: {
  title: ReactNode;
  eyebrow?: ReactNode;
  description?: ReactNode;
  back?: { href: string; label: string };
  actions?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <header className="mb-8 md:mb-10">
      {back && (
        <Link
          href={back.href}
          className="mb-4 inline-flex items-center gap-1.5 text-sm text-text-muted hover:text-foreground transition-colors"
        >
          <ArrowLeft aria-hidden className="w-4 h-4" />
          {back.label}
        </Link>
      )}
      <div className="flex flex-col gap-5 md:flex-row md:items-end md:justify-between">
        <div className="min-w-0 max-w-3xl">
          {eyebrow && (
            <p className="mb-3 font-mono text-[11px] font-semibold uppercase tracking-[0.18em] text-gold">{eyebrow}</p>
          )}
          <h1 className="text-3xl sm:text-4xl md:text-5xl font-black tracking-tight text-foreground text-balance break-words">
            {title}
          </h1>
          {description && <p className="mt-3 text-base md:text-lg text-text-muted text-pretty">{description}</p>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-3 md:shrink-0">{actions}</div>}
      </div>
      {children && <div className="mt-6">{children}</div>}
    </header>
  );
}

/** A section's heading row: the label on the left, an optional link or count on the right. */
export function SectionHeading({
  id,
  children,
  aside,
}: {
  id?: string;
  children: ReactNode;
  aside?: ReactNode;
}) {
  return (
    <div className="mb-4 flex items-baseline justify-between gap-4">
      <h2 id={id} className="text-xs font-bold uppercase tracking-[0.14em] text-text-muted">
        {children}
      </h2>
      {aside && <div className="text-sm">{aside}</div>}
    </div>
  );
}

/** The site's two button looks, as a link. */
export function ButtonLink({
  href,
  variant = "primary",
  external = false,
  children,
}: {
  href: string;
  variant?: "primary" | "secondary";
  external?: boolean;
  children: ReactNode;
}) {
  const look =
    variant === "primary"
      ? "bg-gold text-background hover:brightness-110"
      : "border border-border-bright bg-surface text-foreground hover:border-gold/60 hover:text-gold";
  const className = `inline-flex min-h-10 items-center justify-center gap-2 rounded-lg px-4 text-sm font-semibold transition-all ${look}`;
  return external ? (
    <a href={href} className={className}>
      {children}
    </a>
  ) : (
    <Link href={href} className={className}>
      {children}
    </Link>
  );
}
