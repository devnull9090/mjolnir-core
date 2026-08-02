/**
 * A mod's published releases, newest first.
 *
 * Every row shows what a client needs to decide whether to trust the bytes:
 * version, channel, size, and the SHA-256 the hub recorded at scan time. The
 * action per row differs by host — a download link on the website, an
 * install-this-version button in the launcher — so it arrives as a render
 * prop.
 */
import type { ReactNode } from "react";

import type { Release } from "../types";
import { formatBytes, shortHash, timeAgo } from "./format";
import { Badge } from "./primitives";

export function ReleaseList({
  releases,
  action,
  emptyText = "None published.",
  highlight,
}: {
  releases: Release[];
  action?: (release: Release) => ReactNode;
  emptyText?: string;
  /** Version to mark as the one currently installed. */
  highlight?: string | null;
}) {
  if (releases.length === 0) {
    return <p className="text-sm text-[var(--mj-text-dim)]">{emptyText}</p>;
  }

  return (
    <div className="space-y-2">
      {releases.map((r) => (
        <div key={r.id} className="rounded-lg border border-[var(--mj-border)] p-3">
          <div className="flex items-center justify-between gap-2 mb-1">
            <div className="flex items-center gap-2 min-w-0">
              <span className="font-mono text-sm text-[var(--mj-text)]">v{r.version}</span>
              {r.channel !== "stable" && <Badge tone="amber">{r.channel}</Badge>}
              {highlight === r.version && <Badge tone="green">installed</Badge>}
              {r.signature && (
                <Badge tone="blue" title="Carries an Ed25519 signature over its hash.">
                  signed
                </Badge>
              )}
            </div>
            {action?.(r)}
          </div>
          <div className="text-[11px] text-[var(--mj-text-dim)]">
            {timeAgo(r.created_at)} · {formatBytes(r.file_size)} · {r.download_count} downloads
          </div>
          {r.sha256 && (
            <div
              className="mt-1 font-mono text-[10px] text-[var(--mj-text-dim)] truncate"
              title={`sha256: ${r.sha256}`}
            >
              sha256 {shortHash(r.sha256)}
            </div>
          )}
          {r.changelog_md && (
            <p className="mt-2 text-xs text-[var(--mj-text-muted)] whitespace-pre-wrap break-words line-clamp-6">
              {r.changelog_md}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}
