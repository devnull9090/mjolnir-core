/**
 * A fullscreen viewer for a list of images and videos, opened at one of them.
 *
 * It answers every input the surface has: Escape closes and arrow keys move,
 * because a modal that only answers the mouse is a trap for anyone driving
 * with the keyboard — and a horizontal swipe steps through it, because on a
 * phone the arrows are two small targets over the picture.
 *
 * The caller owns which item is open, so the mod gallery can count views as
 * the index moves and a Markdown page can open it from any image in its body.
 */
import { useCallback, useEffect, useRef } from "react";

import { ChevronLeftIcon, ChevronRightIcon, CloseIcon } from "./icons";

export interface LightboxItem {
  url: string;
  alt: string;
  kind?: "image" | "video";
  /** Dim text after the alt in the caption, e.g. the uploader. */
  detail?: string;
}

export function Lightbox({
  items,
  index,
  onIndexChange,
}: {
  items: LightboxItem[];
  /** The open item, or null when closed. */
  index: number | null;
  onIndexChange: (index: number | null) => void;
}) {
  const dialogRef = useRef<HTMLDivElement>(null);
  const restoreFocus = useRef<HTMLElement | null>(null);
  const touchStart = useRef<{ x: number; y: number } | null>(null);
  const open = index === null ? null : items[index];

  const close = useCallback(() => onIndexChange(null), [onIndexChange]);
  const step = useCallback(
    (dir: 1 | -1) => {
      if (index !== null) onIndexChange((index + dir + items.length) % items.length);
    },
    [index, items.length, onIndexChange],
  );

  useEffect(() => {
    if (index === null) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
      if (e.key === "ArrowRight") step(1);
      if (e.key === "ArrowLeft") step(-1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [index, close, step]);

  // Both of these key off "is it open" rather than which item is open, so
  // stepping through the list does not tear the lock and the focus down and
  // put them straight back up again.
  const isOpen = index !== null;

  // The page behind a fullscreen modal must not scroll under the finger.
  useEffect(() => {
    if (!isOpen) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [isOpen]);

  // Move focus into the dialog on open and hand it back to whatever opened it
  // on close, so keyboard and screen-reader users are not left at the top of
  // the page.
  useEffect(() => {
    if (!isOpen) return;
    restoreFocus.current = document.activeElement as HTMLElement | null;
    dialogRef.current?.focus();
    return () => restoreFocus.current?.focus();
  }, [isOpen]);

  if (!open) return null;

  return (
    <div
      ref={dialogRef}
      tabIndex={-1}
      className="fixed inset-0 z-[100] bg-[var(--mj-bg)]/90 backdrop-blur-sm flex items-center justify-center p-3 sm:p-6 focus:outline-none"
      onClick={close}
      onTouchStart={(e) => {
        const t = e.touches[0];
        touchStart.current = { x: t.clientX, y: t.clientY };
      }}
      onTouchEnd={(e) => {
        const from = touchStart.current;
        touchStart.current = null;
        if (!from || items.length < 2) return;
        const t = e.changedTouches[0];
        const dx = t.clientX - from.x;
        // Only a decisively horizontal swipe pages; anything else is a
        // scroll attempt or a tap, and stealing those would be worse.
        if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(t.clientY - from.y)) {
          step(dx < 0 ? 1 : -1);
        }
      }}
      role="dialog"
      aria-modal="true"
      aria-label={open.alt}
    >
      <button
        type="button"
        aria-label="Close"
        className="absolute top-3 right-3 sm:top-4 sm:right-4 p-2 rounded-full bg-[var(--mj-surface-raised)]/80 text-[var(--mj-text-muted)] hover:text-[var(--mj-text)] cursor-pointer"
        onClick={close}
      >
        <CloseIcon className="w-6 h-6" />
      </button>

      {items.length > 1 && (
        <>
          <button
            type="button"
            aria-label="Previous"
            className="absolute left-2 sm:left-4 top-1/2 -translate-y-1/2 p-3 sm:p-2 rounded-full bg-[var(--mj-surface-raised)]/80 text-[var(--mj-text-muted)] hover:text-[var(--mj-text)] cursor-pointer"
            onClick={(e) => {
              e.stopPropagation();
              step(-1);
            }}
          >
            <ChevronLeftIcon className="w-6 h-6" />
          </button>
          <button
            type="button"
            aria-label="Next"
            className="absolute right-2 sm:right-4 top-1/2 -translate-y-1/2 p-3 sm:p-2 rounded-full bg-[var(--mj-surface-raised)]/80 text-[var(--mj-text-muted)] hover:text-[var(--mj-text)] cursor-pointer"
            onClick={(e) => {
              e.stopPropagation();
              step(1);
            }}
          >
            <ChevronRightIcon className="w-6 h-6" />
          </button>
        </>
      )}

      {/* Wide enough for a side-by-side comparison to read at full size; the
          media's own pixels cap anything smaller. */}
      <figure
        className="max-w-[min(100%,1680px)] max-h-full px-8 sm:px-12"
        onClick={(e) => e.stopPropagation()}
      >
        {open.kind === "video" ? (
          <video
            src={open.url}
            controls
            autoPlay
            playsInline
            className="max-h-[70vh] sm:max-h-[80vh] max-w-full rounded-lg mx-auto"
          />
        ) : (
          // Plain <img>, not next/image: this also renders inside the
          // launcher's Vite build, where next/image does not exist.
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={open.url}
            alt={open.alt}
            className="max-h-[70vh] sm:max-h-[80vh] max-w-full rounded-lg mx-auto"
          />
        )}
        <figcaption className="mt-3 text-center text-xs sm:text-sm text-[var(--mj-text-muted)]">
          {open.alt}
          <span className="text-[var(--mj-text-dim)]">
            {open.detail}
            {items.length > 1 && ` · ${(index ?? 0) + 1} of ${items.length}`}
          </span>
        </figcaption>
      </figure>
    </div>
  );
}
