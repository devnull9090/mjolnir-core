"use client";

import { useEffect, useRef, useState } from "react";

/**
 * A Discord avatar that removes itself when the CDN refuses it, so whatever
 * sits underneath (a seat's initial) shows instead. The stored hash is only
 * refreshed when its owner signs in on the website, so anyone who changed
 * their Discord avatar since then has a hash that 404s. Chrome draws a
 * broken-image icon for a sized `<img>` even with empty alt text.
 *
 * Fetched without credentials: Discord's CDN allows any origin, and an
 * anonymous request keeps its tracking cookie out of the browser (a
 * Lighthouse failure).
 */
export function AvatarImage({ src, className }: { src: string; className?: string }) {
  const ref = useRef<HTMLImageElement>(null);
  const [failed, setFailed] = useState(false);

  // A server-rendered image can finish failing before hydration attaches
  // onError, which then never fires; catch that case on mount.
  useEffect(() => {
    const img = ref.current;
    if (img?.complete && img.naturalWidth === 0) setFailed(true);
  }, []);

  if (failed) return null;
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      ref={ref}
      src={src}
      alt=""
      loading="lazy"
      decoding="async"
      crossOrigin="anonymous"
      onError={() => setFailed(true)}
      className={className}
    />
  );
}
