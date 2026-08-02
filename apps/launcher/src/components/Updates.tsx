/**
 * The update manager: everything that has a newer version, in one list.
 *
 * Selection is the point. "Update all" is one click, but a player who wants
 * the new core install without the mod that changed their weapon balance can
 * tick exactly what they want. Rows say what they are (core, content mod,
 * script mod, tool, the launcher itself) and where they are going, because
 * "update available" without a version is not information.
 */
import { useEffect, useMemo, useState } from "react";
import { ActionButton, Badge, ErrorNote, RefreshIcon, Spinner } from "@mjolnir/hub-kit";

import { KIND_LABEL, type UpdateKind, type UpdatesState } from "../updates/useUpdates";

const KIND_TONE: Record<UpdateKind, "gold" | "blue" | "green" | "neutral"> = {
  launcher: "gold",
  modpack: "gold",
  content: "neutral",
  code: "blue",
  tool: "green",
};

export default function Updates({ updates }: { updates: UpdatesState }) {
  const { items, loading, warnings, progress, applying } = updates;
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [expanded, setExpanded] = useState<string | null>(null);

  // Everything starts ticked: the common case is "yes, all of it", and a
  // player who wants less unticks rather than hunting for a select-all.
  useEffect(() => {
    setSelected(new Set(items.map((i) => i.key)));
  }, [items]);

  const chosen = useMemo(() => items.filter((i) => selected.has(i.key)), [items, selected]);
  const failures = items.filter((i) => progress[i.key]?.status === "failed");

  const toggle = (key: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold">
            {loading
              ? "Checking for updates…"
              : items.length > 0
                ? `${items.length} update${items.length === 1 ? "" : "s"} available`
                : warnings.length > 0
                  ? // Nothing found is not the same as nothing to find when a
                    // source could not be reached; saying otherwise is a lie
                    // a player would only discover in game.
                    "Could not check every source"
                  : "Everything is up to date"}
          </h2>
          <p className="text-sm text-text-secondary mt-0.5">
            The launcher, the core install, your mods and your tools — all of it, in one place.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <ActionButton
            tone="neutral"
            size="sm"
            onClick={() => void updates.refresh()}
            disabled={loading || applying}
          >
            <RefreshIcon className="w-3.5 h-3.5" />
            Check again
          </ActionButton>
          {items.length > 0 && (
            <ActionButton
              onClick={() => void updates.apply(chosen.map((i) => i.key))}
              disabled={applying || chosen.length === 0}
            >
              {applying ? <Spinner className="w-3.5 h-3.5" /> : null}
              {applying
                ? "Updating…"
                : chosen.length === items.length
                  ? `Update all (${items.length})`
                  : `Update selected (${chosen.length})`}
            </ActionButton>
          )}
        </div>
      </div>

      {warnings.length > 0 && (
        <p className="text-sm text-amber-400/90 rounded-lg border border-amber-500/30 bg-amber-500/5 px-4 py-3">
          Could not check {warnings.join(", ")}. Anything listed below is still accurate.
        </p>
      )}

      {failures.length > 0 && (
        <ErrorNote>
          {failures.length === 1
            ? `${failures[0].name} failed: ${progress[failures[0].key]?.error}`
            : `${failures.length} updates failed. See the rows below.`}
        </ErrorNote>
      )}

      {loading && items.length === 0 ? (
        <p className="flex items-center gap-2 text-sm text-text-secondary">
          <Spinner /> Asking every source…
        </p>
      ) : items.length === 0 ? (
        <p className="text-sm text-text-secondary border border-dashed border-border-subtle rounded-xl p-6 text-center">
          {warnings.length > 0
            ? "Nothing out of date among the sources that answered."
            : "Nothing to do. Your install matches what is published."}
        </p>
      ) : (
        <div className="space-y-1.5">
          {items.map((item) => {
            const state = progress[item.key]?.status ?? "idle";
            const isOpen = expanded === item.key;
            return (
              <div
                key={item.key}
                className="bg-surface-secondary border border-border-subtle rounded-xl px-4 py-3"
              >
                <div className="flex items-center gap-3">
                  <input
                    type="checkbox"
                    checked={selected.has(item.key)}
                    onChange={() => toggle(item.key)}
                    disabled={applying}
                    aria-label={`Update ${item.name}`}
                    className="w-4 h-4 accent-mjolnir-gold cursor-pointer"
                  />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-semibold truncate">{item.name}</span>
                      <Badge tone={KIND_TONE[item.kind]}>{KIND_LABEL[item.kind]}</Badge>
                      {item.prerelease && (
                        <Badge
                          tone="amber"
                          title="This mod has no stable release — the newer version is a beta."
                        >
                          beta
                        </Badge>
                      )}
                      {item.restarts && (
                        <Badge tone="amber" title="The launcher will restart itself">
                          restarts
                        </Badge>
                      )}
                    </div>
                    <p className="text-xs text-text-secondary mt-0.5 font-mono">
                      {item.from ? `v${item.from} → ` : ""}
                      <span className="text-mjolnir-gold">v{item.to}</span>
                    </p>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    {item.detail && (
                      <button
                        onClick={() => setExpanded(isOpen ? null : item.key)}
                        className="text-xs text-text-secondary hover:text-text-primary cursor-pointer"
                      >
                        {isOpen ? "Hide notes" : "Notes"}
                      </button>
                    )}
                    {state === "running" ? (
                      <span className="flex items-center gap-1.5 text-xs text-text-secondary">
                        <Spinner className="w-3.5 h-3.5" /> Updating…
                      </span>
                    ) : state === "done" ? (
                      <span className="text-xs text-accent-green">Updated</span>
                    ) : state === "failed" ? (
                      <ActionButton
                        size="sm"
                        tone="danger"
                        disabled={applying}
                        onClick={() => void updates.apply([item.key])}
                      >
                        Retry
                      </ActionButton>
                    ) : (
                      <ActionButton
                        size="sm"
                        disabled={applying}
                        onClick={() => void updates.apply([item.key])}
                      >
                        Update
                      </ActionButton>
                    )}
                  </div>
                </div>

                {state === "failed" && (
                  <p className="mt-2 text-xs text-accent-red break-words">
                    {progress[item.key]?.error}
                  </p>
                )}

                {isOpen && item.detail && (
                  <p className="mt-2 text-xs text-text-secondary whitespace-pre-wrap break-words border-t border-border-subtle pt-2">
                    {item.detail}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
