/**
 * The mod gallery: a strip of screenshots and videos with a lightbox.
 *
 * The lightbox is fully keyboard-driven — Escape closes, arrow keys move —
 * because a modal that only answers the mouse is a trap for anyone driving
 * with the keyboard. Opening an item fires `onView` once per mount, which
 * is how view counts advance without counting every re-render.
 *
 * <ModGallery> adds the community-submission flow: any signed-in user may
 * upload, the item shows immediately to them with an "awaiting review"
 * badge, and it goes public when a moderator approves it.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import { HubError } from "../client";
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
import { Badge, ErrorNote, Spinner } from "./primitives";

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

  if (items.length === 0) return null;

  return (
    <>
      <div className="flex gap-3 overflow-x-auto pb-2">
        {items.map((m, i) => (
          <div key={m.id} className="relative shrink-0 group">
            <button
              type="button"
              onClick={() => setOpenIndex(i)}
              aria-label={m.alt}
              className="block cursor-zoom-in rounded-lg border border-[var(--mj-border)] overflow-hidden hover:border-[var(--mj-gold)]/50 transition-colors"
            >
              {m.kind === "video" ? (
                // preload="metadata" paints the first frame as the poster.
                <video src={m.url} preload="metadata" muted className="h-40 object-cover" />
              ) : (
                // Plain <img>, not next/image: this also renders inside the
                // launcher's Vite build, where next/image does not exist.
                // eslint-disable-next-line @next/next/no-img-element
                <img src={m.url} alt={m.alt} title={m.alt} className="h-40 object-cover" />
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
              <button
                type="button"
                onClick={m.onRemove}
                aria-label={`Remove ${m.alt}`}
                className="absolute top-1.5 right-1.5 p-1 rounded bg-[var(--mj-bg)]/80 text-[var(--mj-text-dim)] hover:text-[var(--mj-red)] opacity-0 group-hover:opacity-100 focus:opacity-100 transition-opacity cursor-pointer"
              >
                <TrashIcon className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        ))}
      </div>

      {open && (
        <div
          className="fixed inset-0 z-[100] bg-[var(--mj-bg)]/90 backdrop-blur-sm flex items-center justify-center p-6"
          onClick={() => setOpenIndex(null)}
          role="dialog"
          aria-modal="true"
          aria-label={open.alt}
        >
          <button
            type="button"
            aria-label="Close"
            className="absolute top-4 right-4 text-[var(--mj-text-muted)] hover:text-[var(--mj-text)] cursor-pointer"
            onClick={() => setOpenIndex(null)}
          >
            <CloseIcon className="w-6 h-6" />
          </button>

          {items.length > 1 && (
            <>
              <button
                type="button"
                aria-label="Previous"
                className="absolute left-4 top-1/2 -translate-y-1/2 p-2 rounded-full bg-[var(--mj-surface-raised)]/80 text-[var(--mj-text-muted)] hover:text-[var(--mj-text)] cursor-pointer"
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
                className="absolute right-4 top-1/2 -translate-y-1/2 p-2 rounded-full bg-[var(--mj-surface-raised)]/80 text-[var(--mj-text-muted)] hover:text-[var(--mj-text)] cursor-pointer"
                onClick={(e) => {
                  e.stopPropagation();
                  step(1);
                }}
              >
                <ChevronRightIcon className="w-6 h-6" />
              </button>
            </>
          )}

          <figure className="max-w-5xl max-h-full" onClick={(e) => e.stopPropagation()}>
            {open.kind === "video" ? (
              <video src={open.url} controls autoPlay className="max-h-[80vh] rounded-lg mx-auto" />
            ) : (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={open.url} alt={open.alt} className="max-h-[80vh] rounded-lg mx-auto" />
            )}
            <figcaption className="mt-3 text-center text-sm text-[var(--mj-text-muted)]">
              {open.alt}
              <span className="text-[var(--mj-text-dim)]">
                {open.uploader ? ` — ${open.uploader}` : ""}
                {open.status === "approved" || !open.status ? ` · ${open.views} views` : ""}
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

const UPLOAD_ACCEPT = "image/png,image/jpeg,image/webp,video/mp4,video/webm";

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
  const [staged, setStaged] = useState<{ file: File; alt: string } | null>(null);
  const [busy, setBusy] = useState(false);
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

  const submit = async () => {
    if (!staged || !staged.alt.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      const created = await client.uploadMedia(slug, staged.file, staged.alt.trim());
      setStaged(null);
      setNotice(
        created.status === "pending"
          ? "Submitted — it will appear publicly once a moderator approves it."
          : "Added to the gallery.",
      );
      load();
    } catch (e) {
      setError(
        e instanceof HubError && e.needsAuth
          ? "Sign in again — that upload was not accepted."
          : e instanceof Error
            ? e.message
            : String(e),
      );
    } finally {
      setBusy(false);
    }
  };

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

      {error && <ErrorNote>{error}</ErrorNote>}
      {notice && <p className="text-xs text-[var(--mj-text-muted)]">{notice}</p>}

      {allowUpload &&
        (user ? (
          staged ? (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs text-[var(--mj-text-muted)] max-w-48 truncate" title={staged.file.name}>
                {staged.file.name}
              </span>
              <input
                autoFocus
                value={staged.alt}
                onChange={(e) => setStaged({ ...staged, alt: e.target.value })}
                onKeyDown={(e) => e.key === "Enter" && void submit()}
                maxLength={500}
                placeholder="Describe it (required)"
                className="flex-1 min-w-40 px-3 py-1.5 text-sm rounded-lg bg-[var(--mj-bg)] border border-[var(--mj-border)] text-[var(--mj-text)] placeholder:text-[var(--mj-text-dim)] focus:border-[var(--mj-gold)]/60 focus:outline-none"
              />
              <button
                type="button"
                onClick={() => void submit()}
                disabled={busy || !staged.alt.trim()}
                className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-[var(--mj-gold)] text-[var(--mj-bg)] disabled:opacity-40 cursor-pointer"
              >
                {busy ? <Spinner className="w-3.5 h-3.5" /> : "Submit"}
              </button>
              <button
                type="button"
                onClick={() => setStaged(null)}
                className="text-xs text-[var(--mj-text-dim)] hover:text-[var(--mj-text)] cursor-pointer"
              >
                Cancel
              </button>
            </div>
          ) : (
            <label className="inline-flex items-center gap-1.5 text-xs text-[var(--mj-gold)] hover:underline cursor-pointer">
              + Add a screenshot or video
              <input
                type="file"
                accept={UPLOAD_ACCEPT}
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) {
                    setStaged({ file, alt: "" });
                    setNotice(null);
                  }
                  e.target.value = "";
                }}
              />
            </label>
          )
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
