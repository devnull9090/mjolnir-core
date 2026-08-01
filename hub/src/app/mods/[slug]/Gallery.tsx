"use client";

import { useState } from "react";
import { X } from "lucide-react";

interface Item {
  id: string;
  url: string;
  alt: string;
}

/** Screenshot strip with a click-to-enlarge lightbox. Alt text everywhere. */
export function Gallery({ items }: { items: Item[] }) {
  const [open, setOpen] = useState<Item | null>(null);

  return (
    <>
      <div className="flex gap-3 overflow-x-auto pb-2">
        {items.map((m) => (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            key={m.id}
            src={m.url}
            alt={m.alt}
            title={m.alt}
            onClick={() => setOpen(m)}
            className="h-40 rounded-lg border border-border object-cover cursor-zoom-in hover:border-gold/50 transition-colors"
          />
        ))}
      </div>

      {open && (
        <div
          className="fixed inset-0 z-[100] bg-background/90 backdrop-blur-sm flex items-center justify-center p-6"
          onClick={() => setOpen(null)}
          role="dialog"
          aria-label={open.alt}
        >
          <button
            aria-label="Close"
            className="absolute top-4 right-4 text-text-muted hover:text-foreground"
            onClick={() => setOpen(null)}
          >
            <X className="w-6 h-6" />
          </button>
          <figure className="max-w-5xl max-h-full">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={open.url} alt={open.alt} className="max-h-[80vh] rounded-lg mx-auto" />
            <figcaption className="mt-3 text-center text-sm text-text-muted">{open.alt}</figcaption>
          </figure>
        </div>
      )}
    </>
  );
}
