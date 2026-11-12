/**
 * Local builds: containers a developer installed with `mjolnir dev install`,
 * which load above every hub mod, and loose containers in Paks that lose to
 * a hub copy (their version never loads). Hidden when there is neither.
 */
import { ActionButton, Badge, ErrorNote } from "@mjolnir/hub-kit";
import { invoke } from "@tauri-apps/api/core";
import { useCallback, useEffect, useState } from "react";

interface LocalBuild {
  name: string;
  file: string;
  chunk: number;
  order: number;
}

interface Shadowed {
  container: string;
  winner: string;
  hub_mod: string | null;
  differing: number;
  identical: number;
}

interface LocalBuilds {
  builds: LocalBuild[];
  shadowed: Shadowed[];
}

export function LocalBuildsPanel() {
  const [data, setData] = useState<LocalBuilds | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setData(await invoke<LocalBuilds>("hub_local_builds"));
      setError(null);
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const remove = async (name: string) => {
    setBusy(name);
    try {
      setData(await invoke<LocalBuilds>("hub_remove_local_build", { name }));
      setError(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(null);
    }
  };

  if (!error && (!data || (data.builds.length === 0 && data.shadowed.length === 0))) return null;

  return (
    <div className="space-y-2 pt-2">
      <div>
        <h3 className="text-lg font-bold">Local builds</h3>
        <p className="text-sm text-text-secondary mt-0.5">
          Installed with <code>mjolnir dev install</code>. They load above every hub mod, newest
          last; a package a build leaves out still loads from the hub.
        </p>
      </div>
      {error && <ErrorNote>{error}</ErrorNote>}
      {data?.builds.map((b) => (
        <div
          key={b.file}
          className="bg-surface-secondary border border-border-subtle rounded-xl px-4 py-2.5 flex flex-wrap items-center gap-x-3 gap-y-2"
        >
          <span className="font-semibold">{b.name}</span>
          <Badge title={b.file}>chunk {b.chunk}</Badge>
          <div className="ml-auto">
            <ActionButton
              size="sm"
              tone="danger"
              disabled={!!busy}
              onClick={() => void remove(b.name)}
            >
              {busy === b.name ? "Removing…" : "Remove"}
            </ActionButton>
          </div>
        </div>
      ))}
      {data && data.shadowed.length > 0 && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 px-4 py-3 text-sm space-y-1">
          <p className="font-semibold text-amber-400">
            These containers in Paks lose to a copy loaded above them, so their version never loads:
          </p>
          <ul className="space-y-0.5">
            {data.shadowed.map((s) => (
              <li key={`${s.container}>${s.winner}`} className="font-mono text-xs">
                {s.container}: {s.differing} chunk{s.differing === 1 ? "" : "s"} differ from{" "}
                {s.hub_mod ?? s.winner}
              </li>
            ))}
          </ul>
          <p className="text-text-secondary">
            To make one win, install it with{" "}
            <code>mjolnir dev install &lt;container&gt; --name &lt;name&gt;</code>.
          </p>
        </div>
      )}
    </div>
  );
}
