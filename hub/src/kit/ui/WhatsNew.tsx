/**
 * "What's new" — the release notes, shown where the update happened.
 *
 * An update that finishes silently leaves a player with a changed application
 * and no account of what changed. This is that account, rendered from the same
 * `changelog/<product>/<version>.md` entry the website and the GitHub release
 * show, so nobody has to go looking for a page to find out what they just
 * installed.
 *
 * Renders `sections` rather than the Markdown body: the desktop apps carry no
 * Markdown renderer, and a modal wants the shape of a release rather than its
 * prose. The full entry is one link away.
 */
import type { ReactNode } from "react";
import { useEffect, useRef } from "react";

import type { ChangelogRelease } from "../changelog";
import { CloseIcon, BoltIcon } from "./icons";
import { Badge, type Tone } from "./primitives";

/** Section headings carry meaning; a security note should not look like a tidy-up. */
const HEADING_TONE: Record<string, Tone> = {
  added: "green",
  changed: "blue",
  fixed: "gold",
  security: "red",
  "known issues": "amber",
};

function toneFor(heading: string): Tone {
  return HEADING_TONE[heading.trim().toLowerCase()] ?? "neutral";
}

export function WhatsNewBody({ releases }: { releases: ChangelogRelease[] }) {
  return (
    <div className="space-y-7">
      {releases.map((release) => (
        <article key={release.tag}>
          <header className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
            <h3 className="text-base font-bold text-[var(--mj-text)]">{release.title}</h3>
            <span className="font-mono text-xs text-[var(--mj-gold)]">v{release.version}</span>
            <span className="text-xs text-[var(--mj-text-dim)]">{release.date}</span>
          </header>
          <p className="mt-1.5 text-sm leading-6 text-[var(--mj-text-muted)]">{release.summary}</p>

          {release.sections.map((section) => (
            <div key={section.heading} className="mt-3">
              <Badge tone={toneFor(section.heading)}>{section.heading}</Badge>
              <ul className="mt-2 space-y-1.5 pl-4">
                {section.items.map((item, i) => (
                  <li
                    key={i}
                    className="list-disc text-sm leading-6 text-[var(--mj-text-muted)] marker:text-[var(--mj-text-dim)]"
                  >
                    {item}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </article>
      ))}
    </div>
  );
}

export interface WhatsNewProps {
  releases: ChangelogRelease[];
  onClose: () => void;
  /**
   * How this surface opens a URL. The website navigates; a desktop app has to
   * hand the link to the system browser, and rendering an `<a>` inside a
   * webview would open it *in* the app with no way back.
   */
  onOpenLink?: (url: string) => void;
  /** Overrides the heading, which otherwise names the product and version. */
  title?: ReactNode;
}

export function WhatsNew({ releases, onClose, onOpenLink, title }: WhatsNewProps) {
  const dialogRef = useRef<HTMLDivElement>(null);

  // Escape closes, and focus moves into the dialog so a keyboard user is not
  // left behind on whatever was focused when the update finished.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    dialogRef.current?.focus();
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  if (releases.length === 0) return null;

  const newest = releases[0];
  const heading =
    title ??
    (releases.length === 1
      ? `${newest.productName} ${newest.version}`
      : `${newest.productName} ${newest.version} — ${releases.length} releases`);

  const changelogUrl = `https://mjolnircore.com${newest.path}`;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 p-4"
      // A backdrop click closes, but a click that started inside the panel and
      // ended on the backdrop (a drag over text) must not.
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label={`What's new in ${newest.productName} ${newest.version}`}
        tabIndex={-1}
        className="flex max-h-[85vh] w-full max-w-2xl flex-col rounded-2xl border border-[var(--mj-border-bright)] bg-[var(--mj-surface)] shadow-2xl outline-none"
      >
        <header className="flex items-start justify-between gap-4 border-b border-[var(--mj-border)] px-6 py-4">
          <div className="flex min-w-0 items-center gap-3">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[var(--mj-gold)]/15 text-[var(--mj-gold)]">
              <BoltIcon className="h-5 w-5" />
            </span>
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase tracking-wide text-[var(--mj-text-dim)]">
                What&apos;s new
              </p>
              <h2 className="truncate text-lg font-bold text-[var(--mj-text)]">{heading}</h2>
            </div>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="shrink-0 cursor-pointer rounded-lg p-1.5 text-[var(--mj-text-dim)] hover:bg-[var(--mj-surface-hover)] hover:text-[var(--mj-text)]"
          >
            <CloseIcon className="h-4 w-4" />
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
          <WhatsNewBody releases={releases} />
        </div>

        <footer className="flex items-center justify-between gap-3 border-t border-[var(--mj-border)] px-6 py-3.5">
          <button
            onClick={() => onOpenLink?.(changelogUrl)}
            className={`text-xs text-[var(--mj-text-muted)] hover:text-[var(--mj-gold)] ${
              onOpenLink ? "cursor-pointer" : "invisible"
            }`}
          >
            Full changelog on mjolnircore.com →
          </button>
          <button
            onClick={onClose}
            className="cursor-pointer rounded-lg bg-[var(--mj-gold)] px-4 py-2 text-sm font-bold text-[var(--mj-bg)] hover:brightness-110"
          >
            Got it
          </button>
        </footer>
      </div>
    </div>
  );
}
