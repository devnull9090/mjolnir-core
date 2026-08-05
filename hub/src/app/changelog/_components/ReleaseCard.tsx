import Link from "next/link";

import type { ChangelogRelease } from "@mjolnir/hub-kit/changelog";

/**
 * One release in a list.
 *
 * The summary is the whole point: a list of version numbers tells a reader
 * nothing, and making them open every entry to find the one that matters is
 * how a changelog stops being read.
 */
export function ReleaseCard({
  release,
  showProduct = false,
}: {
  release: ChangelogRelease;
  showProduct?: boolean;
}) {
  return (
    <Link
      href={release.path}
      className="block rounded-xl border border-border bg-surface-raised p-4 transition-colors hover:border-gold/40 sm:p-5"
    >
      <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
        {showProduct && (
          <span className="rounded bg-surface-hover px-1.5 py-0.5 text-[11px] font-medium text-text-muted">
            {release.productName}
          </span>
        )}
        <span className="font-mono text-sm font-semibold text-gold">v{release.version}</span>
        <time dateTime={release.date} className="text-xs text-text-dim">
          {release.date}
        </time>
      </div>
      <h3 className="mt-2 text-base font-bold text-foreground sm:text-lg">{release.title}</h3>
      <p className="mt-1.5 text-sm leading-6 text-text-muted">{release.summary}</p>
    </Link>
  );
}
