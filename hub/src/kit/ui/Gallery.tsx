/** Screenshot strip with a click-to-enlarge lightbox. Alt text everywhere. */
import { useEffect, useState } from "react";

import { useHub } from "./context";
import { CloseIcon } from "./icons";

export interface GalleryItem {
  id: string;
  url: string;
  alt: string;
}

export function Gallery({ items }: { items: GalleryItem[] }) {
  const [open, setOpen] = useState<GalleryItem | null>(null);

  // Escape closes the lightbox; it is a modal, and a modal that only closes
  // by mouse is a trap for anyone driving with the keyboard.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  if (items.length === 0) return null;

  return (
    <>
      <div className="flex gap-3 overflow-x-auto pb-2">
        {items.map((m) => (
          // Plain <img>, not next/image: this also renders inside the
          // launcher's Vite build, where next/image does not exist.
          // eslint-disable-next-line @next/next/no-img-element
          <img
            key={m.id}
            src={m.url}
            alt={m.alt}
            title={m.alt}
            onClick={() => setOpen(m)}
            className="h-40 rounded-lg border border-[var(--mj-border)] object-cover cursor-zoom-in hover:border-[var(--mj-gold)]/50 transition-colors"
          />
        ))}
      </div>

      {open && (
        <div
          className="fixed inset-0 z-[100] bg-[var(--mj-bg)]/90 backdrop-blur-sm flex items-center justify-center p-6"
          onClick={() => setOpen(null)}
          role="dialog"
          aria-modal="true"
          aria-label={open.alt}
        >
          <button
            type="button"
            aria-label="Close"
            className="absolute top-4 right-4 text-[var(--mj-text-muted)] hover:text-[var(--mj-text)] cursor-pointer"
            onClick={() => setOpen(null)}
          >
            <CloseIcon className="w-6 h-6" />
          </button>
          <figure className="max-w-5xl max-h-full">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={open.url} alt={open.alt} className="max-h-[80vh] rounded-lg mx-auto" />
            <figcaption className="mt-3 text-center text-sm text-[var(--mj-text-muted)]">
              {open.alt}
            </figcaption>
          </figure>
        </div>
      )}
    </>
  );
}

/** The same strip, fetching a mod's media itself. */
export function ModGallery({ slug }: { slug: string }) {
  const { client } = useHub();
  const [items, setItems] = useState<GalleryItem[]>([]);

  useEffect(() => {
    let live = true;
    client
      .listMedia(slug)
      .then((media) => {
        if (!live) return;
        setItems(
          media.map((m) => ({ id: m.id, url: client.absolute(m.url), alt: m.alt_text })),
        );
      })
      .catch(() => setItems([]));
    return () => {
      live = false;
    };
  }, [client, slug]);

  return <Gallery items={items} />;
}
