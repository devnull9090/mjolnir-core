/**
 * Client-side wrapper for the transparency section: fetches what a release
 * declares it changes and hands it to the hook-free <ChangeList>. The
 * launcher's mod page mounts this; the website server-renders <ChangeList>
 * directly and never imports this file into a Server Component.
 */
import { useEffect, useState } from "react";

import type { ReleaseChanges } from "../types";
import { ChangeList } from "./ChangeList";
import { useHub } from "./context";
import { Spinner } from "./primitives";

/** A fetch outcome remembers which release it was for, so switching
 *  releases shows the loading state instead of the previous list. */
type Fetched = { id: string; data: ReleaseChanges | null; error: string | null };

export function ReleaseChangesPanel({ releaseId }: { releaseId: string }) {
  const { client } = useHub();
  const [fetched, setFetched] = useState<Fetched | null>(null);

  useEffect(() => {
    let live = true;
    client
      .getReleaseChanges(releaseId)
      .then((d) => live && setFetched({ id: releaseId, data: d, error: null }))
      .catch(
        (e) =>
          live &&
          setFetched({
            id: releaseId,
            data: null,
            error: e instanceof Error ? e.message : String(e),
          }),
      );
    return () => {
      live = false;
    };
  }, [client, releaseId]);

  const current = fetched && fetched.id === releaseId ? fetched : null;
  if (current?.error) return <p className="text-sm text-[var(--mj-text-dim)]">{current.error}</p>;
  if (!current?.data) {
    return (
      <p className="flex items-center gap-2 text-sm text-[var(--mj-text-dim)]">
        <Spinner /> Loading…
      </p>
    );
  }
  return <ChangeList data={current.data} />;
}
