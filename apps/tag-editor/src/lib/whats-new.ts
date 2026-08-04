/**
 * "What's new" — the editor's own release notes, shown once after it updates.
 *
 * The launcher installs and updates this app, and shows these same notes when
 * it does. That only helps someone who was watching the launcher at the time:
 * the tag editor is normally opened directly, often days later. So it asks the
 * same question here, about itself.
 *
 * The version it compares against is recorded on every run, so the first run
 * after an update is the one that finds a lower recorded version than the
 * running one. A first ever run records silently — someone opening the editor
 * for the first time does not need to be told what changed in it.
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

const PRODUCT = "tag-editor";
const SEEN_KEY = "mjolnir:tag-editor-whatsnew-seen";

/** Over IPC, not the webview: this app's CSP forbids the request. */
const transport = (query: ChangelogQuery) =>
  invoke<ChangelogFeed>("fetch_changelog", {
    product: query.product ?? null,
    since: query.since ?? null,
  });

export interface WhatsNewState {
  releases: ChangelogRelease[];
  dismiss: () => void;
}

export function useWhatsNew(): WhatsNewState {
  const [releases, setReleases] = useState<ChangelogRelease[]>([]);
  /** Recorded when the dialog is dismissed, not when it opens: a crash part-way
   *  through reading should cost a repeat, not the notes. */
  const pending = useRef<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    void (async () => {
      try {
        const version = await getVersion();
        const previous = localStorage.getItem(SEEN_KEY);

        if (!previous) {
          localStorage.setItem(SEEN_KEY, version);
          return;
        }
        if (previous === version) return;

        const feed = await fetchChangelog({ product: PRODUCT, since: previous, transport });
        if (cancelled) return;

        const crossed = releasesBetween(feed.releases, PRODUCT, previous, version);
        if (crossed.length === 0) {
          // Updated to a version with no entry. Nothing to show, but the record
          // still has to move or this runs on every start.
          localStorage.setItem(SEEN_KEY, version);
          return;
        }

        pending.current = version;
        setReleases(crossed);
      } catch {
        // Offline, or the hub is down. The record is deliberately left alone
        // so the next run tries again; this is not worth an error the user has
        // to dismiss before reading a tag.
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  const dismiss = useCallback(() => {
    if (pending.current) localStorage.setItem(SEEN_KEY, pending.current);
    pending.current = null;
    setReleases([]);
  }, []);

  return { releases, dismiss };
}
