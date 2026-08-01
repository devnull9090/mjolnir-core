"use client";

import { useEffect, useRef } from "react";

/**
 * Renders Scalar's API reference against our published spec.
 *
 * Scalar bootstraps itself from a marker <script> tag carrying the config,
 * which doesn't map onto next/script — so both tags are injected imperatively.
 * The classic layout keeps Scalar's own sidebar out of the docs sidebar's way.
 */
export function ScalarDocs({ specUrl }: { specUrl: string }) {
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const host = root.current;
    if (!host) return;

    const config = document.createElement("script");
    config.id = "api-reference";
    config.dataset.url = specUrl;
    config.dataset.configuration = JSON.stringify({ layout: "classic", hideDarkModeToggle: true });
    host.appendChild(config);

    const loader = document.createElement("script");
    loader.src = "https://cdn.jsdelivr.net/npm/@scalar/api-reference";
    host.appendChild(loader);

    return () => {
      host.innerHTML = "";
    };
  }, [specUrl]);

  return <div ref={root} className="scalar-docs min-h-screen" />;
}
