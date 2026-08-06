/**
 * The mod gallery: a strip of screenshots and videos with a lightbox.
 *
 * The lightbox answers every input the surface has: Escape closes and arrow
 * keys move, because a modal that only answers the mouse is a trap for anyone
 * driving with the keyboard — and a horizontal swipe steps through it, because
 * on a phone the arrows are two small targets over the picture. Opening an item
 * fires `onView` once per mount, which is how view counts advance without
 * counting every re-render.
 *
 * <ModGallery> adds the community-submission flow: any signed-in user may
 * upload, the item shows immediately to them with an "awaiting review"
 * badge, and it goes public when a moderator approves it.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import type { Media } from "../types";
import { useHub } from "./context";
import {
  ChevronLeftIcon,
  ChevronRightIcon,
  ClockIcon,
  CloseIcon,
  EyeIcon,
  PlayIcon,
  TrashIcon,
} from "./icons";
import { MediaUploader } from "./MediaUploader";
import { Badge, ErrorNote } from "./primitives";

export interface GalleryItem {
  id: string;
  url: string;
  alt: string;
  kind: "image" | "video";
  views: number;
  /** Moderation state; anything but "approved" renders a badge. */
  status?: "pending" | "approved" | "rejected";
  /** Shown in the lightbox caption when present. */
  uploader?: string | null;
  /** Renders a remove control (own pending/rejected items). */
  onRemove?: () => void;
}

function StatusBadge({ status }: { status: "pending" | "rejected" }) {
  return status === "pending" ? (
    <Badge tone="amber" title="Visible only to you until a moderator approves it.">
      <ClockIcon className="w-3 h-3" />
      awaiting review
    </Badge>
  ) : (
    <Badge tone="red" title="A moderator rejected this item. Only you can see it.">
      rejected
    </Badge>
  );
}

export function Gallery({
  items,
  onView,
}: {
  items: GalleryItem[];
  onView?: (item: GalleryItem) => void;
}) {
  const [openIndex, setOpenIndex] = useState<number | null>(null);
  const viewed = useRef(new Set<string>());
  const dialogRef = useRef<HTMLDivElement>(null);
  const restoreFocus = useRef<HTMLElement | null>(null);
  const touchStart = useRef<{ x: number; y: number } | null>(null);
  const open = openIndex === null ? null : items[openIndex];

  // One view per item per mount, however many times the lightbox lands on it.
  useEffect(() => {
    if (!open || viewed.current.has(open.id)) return;
    viewed.current.add(open.id);
    onView?.(open);
  }, [open, onView]);

  const step = useCallback(
    (dir: 1 | -1) =>
      setOpenIndex((i) => (i === null ? null : (i + dir + items.length) % items.length)),
    [items.length],
  );

  useEffect(() => {
    if (openIndex === null) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpenIndex(null);
      if (e.key === "ArrowRight") step(1);
      if (e.key === "ArrowLeft") step(-1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [openIndex, step]);

  // Both of these key off "is it open" rather than which item is open, so
  // stepping through the gallery does not tear the lock and the focus down
  // and put them straight back up again.
  const isOpen = openIndex !== null;

  // The page behind a fullscreen modal must not scroll under the finger.
  useEffect(() => {
    if (!isOpen) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, [isOpen]);

  // Move focus into the dialog on open and hand it back to the tile on close,
  // so keyboard and screen-reader users are not left at the top of the page.
  useEffect(() => {
    if (!isOpen) return;
    restoreFocus.current = document.activeElement as HTMLElement | null;
    dialogRef.current?.focus();
    return () => restoreFocus.current?.focus();
  }, [isOpen]);

  if (items.length === 0) return null;

  return (
    <>
      <div className="flex gap-3 overflow-x-auto pb-2 snap-x snap-mandatory">
        {items.map((m, i) => (
          <div key={m.id} className="relative shrink-0 snap-start group">
            <button
              type="button"
              onClick={() => setOpenIndex(i)}
              aria-label={m.alt}
              className="block cursor-zoom-in rounded-lg border border-[var(--mj-border)] overflow-hidden hover:border-[var(--mj-gold)]/50 transition-colors"
            >
              {m.kind === "video" ? (
                // preload="metadata" paints the first frame as the poster.
                <video src={m.url} preload="metadata" muted className="h-32 sm:h-40 object-cover" />
              ) : (
                // Plain <img>, not next/image: this also renders inside the
                // launcher's Vite build, where next/image does not exist.
                // eslint-disable-next-line @next/next/no-img-element
                <img src={m.url} alt={m.alt} title={m.alt} className="h-32 sm:h-40 object-cover" />
              )}
              {m.kind === "video" && (
                <span className="absolute inset-0 flex items-center justify-center pointer-events-none">
                  <span className="rounded-full bg-[var(--mj-bg)]/70 p-3">
                    <PlayIcon filled className="w-6 h-6 text-[var(--mj-text)]" />
                  </span>
                </span>
              )}
              {m.status && m.status !== "approved" ? (
                <span className="absolute top-1.5 left-1.5">
                  <StatusBadge status={m.status} />
                </span>
              ) : (
                <span className="absolute bottom-1.5 right-1.5 inline-flex items-center gap-1 rounded bg-[var(--mj-bg)]/75 px-1.5 py-0.5 text-[10px] text-[var(--mj-text-muted)]">
                  <EyeIcon className="w-3 h-3" />
                  {m.views}
                </span>
              )}
            </button>
            {m.onRemove && (
              // Always visible on a touch screen: hover reveals nothing there,
              // and a control you cannot summon is a control you do not have.
              <button
                type="button"
                onClick={m.onRemove}
                aria-label={`Remove ${m.alt}`}
                className="absolute top-1.5 right-1.5 p-2 sm:p-1 rounded bg-[var(--mj-bg)]/80 text-[var(--mj-text-dim)] hover:text-[var(--mj-red)] sm:opacity-0 sm:group-hover:opacity-100 sm:focus:opacity-100 transition-opacity cursor-pointer"
              >
                <TrashIcon className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        ))}
      </div>

      {open && (
        <div
          ref={dialogRef}
          tabIndex={-1}
          className="fixed inset-0 z-[100] bg-[var(--mj-bg)]/90 backdrop-blur-sm flex items-center justify-center p-3 sm:p-6 focus:outline-none"
          onClick={() => setOpenIndex(null)}
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
            onClick={() => setOpenIndex(null)}
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

          <figure className="max-w-5xl max-h-full px-8 sm:px-12" onClick={(e) => e.stopPropagation()}>
            {open.kind === "video" ? (
              <video
                src={open.url}
                controls
                autoPlay
                playsInline
                className="max-h-[70vh] sm:max-h-[80vh] max-w-full rounded-lg mx-auto"
              />
            ) : (
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
                {open.uploader ? ` — ${open.uploader}` : ""}
                {open.status === "approved" || !open.status ? ` · ${open.views} views` : ""}
                {items.length > 1 && ` · ${(openIndex ?? 0) + 1} of ${items.length}`}
              </span>
            </figcaption>
          </figure>
        </div>
      )}
    </>
  );
}

function toItem(m: Media): GalleryItem {
  return {
    id: m.id,
    url: m.url,
    alt: m.alt_text,
    kind: m.kind === "video" ? "video" : "image",
    views: m.view_count,
    status: m.status,
    uploader: m.uploader,
  };
}

/**
 * The full community gallery for one mod: the strip above, wired to the
 * API, plus the submission flow when `allowUpload` is set. Off by default
 * because a host's transport must carry FormData to upload — the website's
 * does; the launcher's Tauri bridge does not yet.
 */
export function ModGallery({
  slug,
  allowUpload = false,
  initial,
}: {
  slug: string;
  allowUpload?: boolean;
  initial?: Media[];
}) {
  const { client, user, signIn } = useHub();
  const [media, setMedia] = useState<Media[]>(initial ?? []);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(() => {
    client
      .listMedia(slug)
      .then((m) => {
        setMedia(m);
        setError(null);
      })
      .catch(() => setMedia((prev) => prev));
  }, [client, slug]);

  // Refetch when the identity changes: the list carries the caller's own
  // pending submissions, so it depends on who is asking.
  useEffect(load, [load, user?.id]);

  // Uploaded items are appended straight away rather than refetched: the
  // submitter should see their screenshot land the moment it finishes.
  const onUploaded = useCallback((created: Media) => {
    setMedia((prev) => [...prev, created]);
    setNotice(
      created.status === "pending"
        ? "Submitted — it will appear publicly once a moderator approves it."
        : "Added to the gallery.",
    );
  }, []);

  const remove = async (id: string) => {
    try {
      await client.deleteMedia(id);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const items = media.map((m) => ({
    ...toItem(m),
    onRemove:
      user && m.uploader_id === user.id && m.status !== "approved"
        ? () => void remove(m.id)
        : undefined,
  }));

  const onView = useCallback(
    (item: GalleryItem) => {
      if (item.status && item.status !== "approved") return;
      client
        .recordMediaView(item.id)
        .then(({ views }) =>
          setMedia((prev) => prev.map((m) => (m.id === item.id ? { ...m, view_count: views } : m))),
        )
        .catch(() => {});
    },
    [client],
  );

  return (
    <div className="space-y-3">
      <Gallery items={items} onView={onView} />

      {items.length === 0 && (
        <p className="text-xs text-[var(--mj-text-dim)]">
          No screenshots yet{allowUpload && user ? " — add the first one." : "."}
        </p>
      )}

      {error && <ErrorNote>{error}</ErrorNote>}
      {notice && <p className="text-xs text-[var(--mj-text-muted)]">{notice}</p>}

      {allowUpload &&
        (user ? (
          <MediaUploader slug={slug} variant="inline" onUploaded={onUploaded} />
        ) : (
          <button
            type="button"
            onClick={signIn}
            className="text-xs text-[var(--mj-gold)] hover:underline cursor-pointer"
          >
            Sign in to add screenshots or videos
          </button>
        ))}
    </div>
  );
}
