/**
 * The mod gallery: a strip of screenshots and videos that open in the
 * <Lightbox>. Opening an item fires `onView` once per mount, which is how view
 * counts advance without counting every re-render.
 *
 * <MediaGallery> adds the submission flow on top, against whichever owner it
 * is given — a mod, where any signed-in user may upload and the item shows
 * immediately to them with an "awaiting review" badge until a moderator
 * approves it, or a tool, where moderators curate and everyone else reads.
 * <ModGallery> and <ToolGallery> are those two policies, named.
 */
import { useCallback, useEffect, useRef, useState } from "react";

import type { Media, MediaOwner } from "../types";
import { useHub } from "./context";
import { ClockIcon, EyeIcon, PlayIcon, TrashIcon } from "./icons";
import { Lightbox } from "./Lightbox";
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
  const open = openIndex === null ? null : items[openIndex];

  // One view per item per mount, however many times the lightbox lands on it.
  useEffect(() => {
    if (!open || viewed.current.has(open.id)) return;
    viewed.current.add(open.id);
    onView?.(open);
  }, [open, onView]);

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

      <Lightbox
        items={items.map((m) => ({
          url: m.url,
          alt: m.alt,
          kind: m.kind,
          detail:
            (m.uploader ? ` — ${m.uploader}` : "") +
            (m.status === "approved" || !m.status ? ` · ${m.views} views` : ""),
        }))}
        index={openIndex}
        onIndexChange={setOpenIndex}
      />
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
 * The full gallery for one mod or tool: the strip above, wired to the API,
 * plus the submission flow.
 *
 * `uploads` is the policy, not just a switch, because the two owners differ:
 * anyone signed in may submit to a mod (and is invited to sign in), while a
 * tool's previews are moderator-only and nobody else is asked. "nobody"
 * turns the flow off entirely — which is what the launcher gets, since its
 * Tauri transport cannot carry FormData yet.
 */
export function MediaGallery({
  owner,
  uploads = "nobody",
  initial,
}: {
  owner: MediaOwner;
  uploads?: "anyone" | "moderators" | "nobody";
  initial?: Media[];
}) {
  const { client, user, signIn } = useHub();
  const [media, setMedia] = useState<Media[]>(initial ?? []);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const moderator = !!user && user.role !== "user";
  const mayUpload = uploads === "anyone" ? !!user : uploads === "moderators" && moderator;
  // Only a gallery anyone may add to has anything to gain by asking a
  // signed-out reader to sign in.
  const inviteSignIn = uploads === "anyone" && !user;

  // Keyed on the two primitives rather than on `owner`, so a caller writing
  // the object inline does not re-arm the fetch on every render.
  const { type, slug } = owner;
  const load = useCallback(() => {
    client
      .listMedia({ type, slug })
      .then((m) => {
        setMedia(m);
        setError(null);
      })
      .catch(() => setMedia((prev) => prev));
  }, [client, type, slug]);

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
    // Your own unreviewed submissions, always; anything at all when you are
    // the moderator who curates this gallery.
    onRemove:
      (user && m.uploader_id === user.id && m.status !== "approved") ||
      (moderator && uploads === "moderators")
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
          No screenshots yet{mayUpload ? " — add the first one." : "."}
        </p>
      )}

      {error && <ErrorNote>{error}</ErrorNote>}
      {notice && <p className="text-xs text-[var(--mj-text-muted)]">{notice}</p>}

      {mayUpload && (
        <MediaUploader owner={{ type, slug }} variant="inline" onUploaded={onUploaded} />
      )}

      {inviteSignIn && (
        <button
          type="button"
          onClick={signIn}
          className="text-xs text-[var(--mj-gold)] hover:underline cursor-pointer"
        >
          Sign in to add screenshots or videos
        </button>
      )}
    </div>
  );
}

/**
 * A mod's community gallery. Upload is off by default because a host's
 * transport must carry FormData to submit — the website's does; the
 * launcher's Tauri bridge does not yet.
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
  return (
    <MediaGallery
      owner={{ type: "mod", slug }}
      uploads={allowUpload ? "anyone" : "nobody"}
      initial={initial}
    />
  );
}

/**
 * A tool's preview gallery. Tools are first-party and defined in code, so
 * their screenshots are curated: moderators add and remove, everyone else
 * reads.
 */
export function ToolGallery({ slug, initial }: { slug: string; initial?: Media[] }) {
  return <MediaGallery owner={{ type: "tool", slug }} uploads="moderators" initial={initial} />;
}
