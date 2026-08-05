/**
 * "What's new" — release notes shown once, where the update happened.
 *
 * An update that finishes silently leaves a player with a changed launcher and
 * no account of what changed. Two things trigger the dialog, because updates
 * arrive two different ways:
 *
 *   - **The launcher itself** restarts to finish updating, so there is no
 *     "after" to show anything in. It is handled at startup instead: the
 *     version is recorded on every boot, and a boot that finds a lower recorded
 *     version than the running one is the first boot after an update.
 *   - **Everything else** — the runtime, tools like the tag editor — applies
 *     in place, so the dialog opens when the run finishes.
 *
 * Seen versions are recorded per product, so being shown notes is not a
 * side effect of the dialog rendering: it is recorded when the dialog is
 * dismissed, and a crash mid-read means seeing them again rather than never.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { getVersion } from "@tauri-apps/api/app";
import {
  fetchChangelog,
  releasesBetween,
  type ChangelogFeed,
  type ChangelogQuery,
  type ChangelogRelease,
} from "@mjolnir/hub-kit";

import type { UpdateItem } from "./useUpdates";

const SEEN_KEY = "mjolnir:whatsnew-seen";

/**
 * Requests go through Rust, not the webview — see src-tauri/src/changelog.rs.
 */
const transport = (query: ChangelogQuery) =>
  invoke<ChangelogFeed>("fetch_changelog", {
    product: query.product ?? null,
    since: query.since ?? null,
  });

type SeenVersions = Record<string, string>;

function readSeen(): SeenVersions {
  try {
    const raw = localStorage.getItem(SEEN_KEY);
    return raw ? (JSON.parse(raw) as SeenVersions) : {};
  } catch {
    // A corrupt record must not stop the launcher starting. Losing it costs
    // one duplicate dialog.
    return {};
  }
}

function writeSeen(next: SeenVersions) {
  try {
    localStorage.setItem(SEEN_KEY, JSON.stringify(next));
  } catch {
    /* Private mode, full disk: not worth a failure the player can act on. */
  }
}

/**
 * Which changelog a finished update belongs to.
 *
 * Only products that publish one. Content and script mods carry their own
 * per-mod versions from the hub, which are not the version the code-mod *set*
 * releases under, so mapping them here would show notes for the wrong thing.
 */
function productFor(item: UpdateItem): string | null {
  if (item.kind === "modpack") return "runtime";
  if (item.kind === "tool") return item.key.slice("tool:".length);
  return null;
}

export interface WhatsNewState {
  releases: ChangelogRelease[];
  dismiss: () => void;
  /** Called with the items an update run actually completed. */
  announce: (completed: UpdateItem[]) => Promise<void>;
}

export function useWhatsNew(): WhatsNewState {
  const [releases, setReleases] = useState<ChangelogRelease[]>([]);
  /** What the pending dialog will record once it is dismissed. */
  const pending = useRef<SeenVersions>({});

  const show = useCallback((found: ChangelogRelease[], seen: SeenVersions) => {
    if (found.length === 0) return;
    pending.current = { ...pending.current, ...seen };
    setReleases((current) => (current.length > 0 ? current : found));
  }, []);

  // The launcher's own update: it restarted, so this is the first boot after.
  useEffect(() => {
    let cancelled = false;

    void (async () => {
      try {
        const version = await getVersion();
        const seen = readSeen();
        const previous = seen.launcher ?? null;

        // A first run has nothing to compare against and nothing to say: a
        // player opening the launcher for the first time does not need to be
        // told what changed in it. Record where they started.
        if (!previous) {
          writeSeen({ ...seen, launcher: version });
          return;
        }
        if (previous === version) return;

        const feed = await fetchChangelog({ product: "launcher", since: previous, transport });
        if (cancelled) return;

        const crossed = releasesBetween(feed.releases, "launcher", previous, version);
        if (crossed.length === 0) {
          // Updated to a version with no entry — nothing to show, but the
          // record still has to move or this runs again on every boot.
          writeSeen({ ...seen, launcher: version });
          return;
        }
        show(crossed, { launcher: version });
      } catch {
        // Offline, or the hub is down. The update still happened; the notes
        // are not worth an error dialog, and the record is deliberately left
        // alone so the next boot tries again.
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [show]);

  const announce = useCallback(
    async (completed: UpdateItem[]) => {
      const seen = readSeen();
      const found: ChangelogRelease[] = [];
      const recorded: SeenVersions = {};

      await Promise.all(
        completed.map(async (item) => {
          const product = productFor(item);
          if (!product) return;

          // `from` is what was installed, which the update manager already
          // knows. Null means it was not recorded, and without a starting
          // point there is no range to describe.
          const from = item.from;
          if (!from) {
            recorded[product] = item.to;
            return;
          }

          try {
            const feed = await fetchChangelog({ product, since: from, transport });
            found.push(...releasesBetween(feed.releases, product, from, item.to));
            recorded[product] = item.to;
          } catch {
            /* Leave the record alone so it can be picked up next time. */
          }
        }),
      );

      if (found.length === 0) {
        // Nothing to show, but versions that resolved still move forward.
        if (Object.keys(recorded).length > 0) writeSeen({ ...seen, ...recorded });
        return;
      }

      found.sort((a, b) => b.date.localeCompare(a.date));
      show(found, recorded);
    },
    [show],
  );

  const dismiss = useCallback(() => {
    const seen = readSeen();
    writeSeen({ ...seen, ...pending.current });
    pending.current = {};
    setReleases([]);
  }, []);

  return { releases, dismiss, announce };
}
