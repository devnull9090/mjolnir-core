"use client";

import { useCallback, useRef, useState, type MouseEvent, type ReactNode } from "react";
import { Lightbox, type LightboxItem } from "@mjolnir/hub-kit";

/**
 * Opens any `[data-zoom]` image inside it in the hub's lightbox, stepping
 * through every other one on the page.
 *
 * The Markdown around it stays a server component: this only listens for
 * clicks bubbling up from the buttons it renders, and reads the list of images
 * from the DOM when one is clicked, so a page pays for no client-side copy of
 * its body.
 */
export function ZoomableImages({ children }: { children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const [items, setItems] = useState<LightboxItem[]>([]);
  const [index, setIndex] = useState<number | null>(null);

  const onClick = useCallback((e: MouseEvent) => {
    const trigger = (e.target as HTMLElement).closest("[data-zoom]");
    // An image an author wrapped in a link goes where the link says.
    if (!trigger || trigger.closest("a") || !ref.current) return;
    const imgs = Array.from(ref.current.querySelectorAll<HTMLImageElement>("[data-zoom] img"));
    const at = imgs.indexOf(trigger.querySelector("img")!);
    if (at < 0) return;
    setItems(imgs.map((img) => ({ url: img.currentSrc || img.src, alt: img.alt })));
    setIndex(at);
  }, []);

  return (
    <div ref={ref} onClick={onClick}>
      {children}
      <Lightbox items={items} index={index} onIndexChange={setIndex} />
    </div>
  );
}
