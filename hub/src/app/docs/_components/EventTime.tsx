"use client";

import { useSyncExternalStore, type ReactNode } from "react";

// A reader's time zone doesn't change under them, so there is nothing to watch.
const subscribe = () => () => {};

/**
 * An event's time as the author wrote it, then the same moment in the reader's
 * own time zone. Written in Markdown as a link whose title is an exact time, so
 * the post still reads on GitHub and the time still opens the event:
 *
 *   [Saturday, November 7, 6 PM MST](https://discord.gg/x?event=1 "2026-11-08T01:00:00Z")
 *
 * The server can't know the reader's zone, so it sends the author's text alone
 * and the browser adds the local time when it hydrates.
 */
export function EventTime({ at, children }: { at: string; children: ReactNode }) {
  const local = useSyncExternalStore(
    subscribe,
    () =>
      new Date(at).toLocaleString(undefined, {
        weekday: "long",
        month: "long",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
        timeZoneName: "short",
      }),
    () => null,
  );
  return (
    <>
      <time dateTime={at}>{children}</time>
      {local && (
        <>
          {" "}
          (your time: <strong className="font-bold text-foreground">{local}</strong>)
        </>
      )}
    </>
  );
}
