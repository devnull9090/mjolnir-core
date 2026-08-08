"use client";

import { useEffect, useState } from "react";
import { Check, Copy, ExternalLink, Hash } from "lucide-react";

import type { ToolRelease } from "@/lib/tools";

/**
 * What the tool's release manifest currently advertises: the version, the
 * download size, and the SHA-256 the launcher checks the bytes against.
 *
 * Fetched in the browser for the same reason the launcher download page does
 * it — the page itself is rendered from local data and must not wait on the
 * CDN. When the manifest cannot be read this renders the version the
 * changelog knows about and nothing else, rather than an error.
 */

function formatSize(bytes: number): string {
  const mb = bytes / (1024 * 1024);
  return mb >= 10 ? `${Math.round(mb)} MB` : `${mb.toFixed(1)} MB`;
}

export function LatestBuild({
  slug,
  fallbackVersion,
}: {
  slug: string;
  fallbackVersion: string | null;
}) {
  const [release, setRelease] = useState<ToolRelease | null>(null);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let live = true;
    fetch("/api/tools/latest")
      .then((res) => res.json())
      .then((json: { tools: ToolRelease[] }) => {
        if (!live) return;
        setRelease(json.tools?.find((t) => t.id === slug) ?? null);
      })
      .catch((err) => console.error("Failed to load the tool manifest:", err))
      .finally(() => {
        if (live) setLoading(false);
      });
    return () => {
      live = false;
    };
  }, [slug]);

  const version = release?.version ?? fallbackVersion;
  const hash = release?.sha256 ?? null;

  const copy = () => {
    if (!hash) return;
    navigator.clipboard.writeText(hash);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="rounded-xl border border-border bg-surface-card p-3 sm:p-4">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
        <span className="text-text-dim">Latest build</span>
        {version ? (
          <span className="font-mono font-bold text-gold">v{version}</span>
        ) : (
          <span className="text-text-dim">unknown</span>
        )}
        {release?.size && (
          <>
            <span className="text-text-dim">·</span>
            <span className="text-text-muted">{formatSize(release.size)}</span>
          </>
        )}
        {loading && (
          <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-gold border-t-transparent" />
        )}
      </div>

      {hash && (
        <div className="mt-3">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <span className="flex min-w-0 items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-gold">
              <Hash className="h-3.5 w-3.5 flex-shrink-0" />
              <span>SHA-256</span>
              {/* The file name is a file name, not a heading — the uppercase
                  on the label above must not reach it. */}
              {release?.exe && (
                <span className="break-all font-mono normal-case text-text-muted">
                  {release.exe}
                </span>
              )}
            </span>
            <button
              onClick={copy}
              className="flex flex-shrink-0 cursor-pointer items-center gap-1.5 rounded-md border border-border-bright bg-surface-raised px-3 py-2 text-xs text-text-muted transition-all hover:border-gold/40 hover:text-foreground"
            >
              {copied ? (
                <>
                  <Check className="h-3.5 w-3.5 text-accent-green" />
                  <span className="font-semibold text-accent-green">Copied!</span>
                </>
              ) : (
                <>
                  <Copy className="h-3.5 w-3.5" />
                  Copy
                </>
              )}
            </button>
          </div>
          <code className="block break-all rounded border border-border/50 bg-background p-2.5 font-mono text-xs text-gold">
            {hash}
          </code>
        </div>
      )}

      {release && (
        <a
          href={release.checksums_url}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-3 inline-flex items-center gap-1 text-xs text-accent-blue hover:underline"
        >
          View raw checksums.txt
          <ExternalLink className="h-3 w-3" />
        </a>
      )}
    </div>
  );
}
