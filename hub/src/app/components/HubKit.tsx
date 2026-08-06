"use client";

/**
 * The client boundary for shared hub-kit components.
 *
 * The kit is bundler-agnostic source with no `"use client"` directives of
 * its own — the launcher bundles it with Vite, which has no such concept and
 * warns about stray directives. This file is where those components become
 * client components for the app router; server pages import them from here.
 */
import { Download } from "lucide-react";
import { createHubClient, formatBytes, HubProvider, ReleaseList } from "@mjolnir/hub-kit";
import type { Release } from "@mjolnir/hub-kit";
import { useEffect, type ReactNode } from "react";

export {
  CommentThread,
  Gallery,
  ModCard,
  ModGallery,
  RatingPanel,
  ReleaseList,
  ReportButton,
  Stars,
  useHub,
} from "@mjolnir/hub-kit";

/**
 * Same-origin client: an empty base URL means "this site", and the browser
 * attaches the Discord session cookie. Created once at module scope because
 * it holds no per-render state.
 */
const client = createHubClient({});

/** Mounted once in the root layout; every kit component reads from it. */
export function HubKitProvider({ children }: { children: ReactNode }) {
  return <HubProvider client={client}>{children}</HubProvider>;
}

/**
 * Counts a mod page view once per mount. The server folds repeats per
 * viewer per hour, so this needs no client-side bookkeeping.
 */
export function ModViewBeacon({ slug }: { slug: string }) {
  useEffect(() => {
    client.recordModView(slug).catch(() => {});
  }, [slug]);
  return null;
}

/**
 * `<ReleaseList>` takes its per-row action as a render prop, and a function
 * cannot be handed from a server component to a client one. The website's
 * action — a download link — therefore lives on this side of the boundary,
 * and server pages pass only the releases.
 */
export function ReleaseDownloadList({ releases }: { releases: Release[] }) {
  return (
    <ReleaseList
      releases={releases}
      action={(r) => (
        <a
          href={`/api/v1/releases/${r.id}/download`}
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold bg-gold/10 text-gold hover:bg-gold/20 transition-colors"
        >
          <Download className="w-3 h-3" />
          {formatBytes(r.file_size)}
        </a>
      )}
    />
  );
}
