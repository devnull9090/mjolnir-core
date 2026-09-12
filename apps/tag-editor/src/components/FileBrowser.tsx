import { useState } from "react";
import { useEditor } from "../stores/editor-store";
import { copyText } from "../lib/clipboard";
import { showContextMenu } from "./ContextMenu";
import { Spinner } from "./LoadingPanel";
import type { DirEntry } from "../lib/api";

/** Bytes, at the precision a file listing actually needs. */
function humanSize(bytes: number): string {
  if (bytes === 0) return "";
  const units = ["B", "KB", "MB", "GB"];
  let n = bytes;
  let u = 0;
  while (n >= 1024 && u < units.length - 1) {
    n /= 1024;
    u += 1;
  }
  return `${n < 10 && u > 0 ? n.toFixed(1) : Math.round(n)} ${units[u]}`;
}

/** Clickable path segments, so any ancestor is one click away. */
function Breadcrumbs() {
  const dir = useEditor((s) => s.dir);
  const openDir = useEditor((s) => s.openDir);
  const segments = dir === "" ? [] : dir.split("/");

  return (
    <div className="flex flex-wrap items-center gap-0.5 px-3 py-2 font-mono text-[11px]">
      <button
        type="button"
        onClick={() => void openDir("")}
        className={
          segments.length === 0
            ? "text-mjolnir-gold"
            : "text-text-secondary hover:text-text-primary"
        }
        title="Everything"
      >
        all
      </button>
      {segments.map((seg, i) => {
        const path = segments.slice(0, i + 1).join("/");
        const last = i === segments.length - 1;
        return (
          <span key={path} className="flex items-center gap-0.5">
            <span className="text-text-dim">/</span>
            <button
              type="button"
              onClick={() => void openDir(path)}
              className={
                last ? "text-mjolnir-gold" : "text-text-secondary hover:text-text-primary"
              }
            >
              {seg}
            </button>
          </span>
        );
      })}
    </div>
  );
}

/** One row: a folder to descend into, or an asset to open in a tab. */
function Row({ entry, showPath }: { entry: DirEntry; showPath: boolean }) {
  const openDir = useEditor((s) => s.openDir);
  const openTab = useEditor((s) => s.openTab);
  const openNewTag = useEditor((s) => s.openNewTag);
  const tabs = useEditor((s) => s.tabs);
  const loadedSet = useEditor((s) => s.liveLoadedSet);

  const isDir = entry.kind === "dir";
  // A census marked this tag as loaded in the running game right now, so a
  // live edit to it lands instantly.
  const inGame = entry.kind === "tag" && entry.index !== null && loadedSet.has(entry.index);
  // Anything that is not a folder opens as a document of its own kind.
  const kind = entry.kind === "dir" ? "tag" : entry.kind;
  const open = isDir
    ? () => void openDir(entry.path)
    : () => void openTab(kind, entry.index ?? 0, entry.name, { path: entry.path });

  const isOpen = !isDir && tabs.some((t) => t.kind === kind && t.index === entry.index);

  // In search results the name alone is ambiguous, so show where it lives.
  const parent = entry.path.slice(0, Math.max(0, entry.path.lastIndexOf("/")));

  return (
    <li>
      <button
        type="button"
        onDoubleClick={open}
        onClick={open}
        onContextMenu={(e) =>
          showContextMenu(e, [
            { label: "Open", action: open },
            { label: "Copy Path", action: () => void copyText(entry.path) },
            // A tag row reads `tags/<short>.<group>`; the New Tag dialog
            // wants the two halves.
            ...(entry.kind === "tag" && entry.index !== null
              ? [
                  {
                    label: "New Tag From This…",
                    action: () => {
                      const rel = entry.path.replace(/^tags\//, "");
                      const dot = rel.lastIndexOf(".");
                      openNewTag({
                        index: entry.index ?? 0,
                        group: dot < 0 ? "" : rel.slice(dot + 1),
                        short: dot < 0 ? rel : rel.slice(0, dot),
                      });
                    },
                  },
                ]
              : []),
          ])
        }
        title={entry.path}
        className={`flex w-full items-baseline gap-2 px-3 py-1.5 text-left transition-colors hover:bg-surface-hover ${
          isOpen ? "text-mjolnir-gold" : "text-text-secondary"
        }`}
      >
        <span
          className={`w-4 shrink-0 text-center font-mono text-[10px] ${
            isDir
              ? "text-text-dim"
              : entry.kind === "texture"
                ? "text-accent-blue"
                : entry.kind === "sound"
                  ? "text-accent-green"
                  : entry.kind === "mesh"
                    ? "text-accent-purple"
                    : "text-mjolnir-gold/70"
          }`}
        >
          {isDir
            ? "▸"
            : entry.kind === "texture"
              ? "▣"
              : entry.kind === "sound"
                ? "♪"
                : entry.kind === "mesh"
                  ? "◈"
                  : "◆"}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate font-mono text-xs">{entry.name}</span>
          {showPath && parent && (
            <span className="block truncate font-mono text-[10px] text-text-dim">{parent}</span>
          )}
        </span>
        {inGame && (
          <span
            title="Loaded in the running game — live edits to this tag are instant"
            className="shrink-0 font-mono text-[9px] text-accent-green"
          >
            ●
          </span>
        )}
        <span className="shrink-0 font-mono text-[10px] text-text-dim">
          {isDir ? `${entry.children ?? 0} item${entry.children === 1 ? "" : "s"}` : humanSize(entry.size)}
        </span>
      </button>
    </li>
  );
}

/**
 * A file-dialog view over the cooked assets.
 *
 * The game ships no directories — every asset is a flat chunk in a container —
 * so the tree is derived from package paths. Navigating is per-directory;
 * typing searches the whole tree at once.
 */
export function FileBrowser() {
  const { dir, entries, dirLoading, fileQuery } = useEditor();
  const openDir = useEditor((s) => s.openDir);
  const searchFiles = useEditor((s) => s.searchFiles);
  const liveLoaded = useEditor((s) => s.liveLoaded);
  const [showLoaded, setShowLoaded] = useState(false);

  const searching = fileQuery.trim() !== "";
  const parent = dir.slice(0, Math.max(0, dir.lastIndexOf("/")));

  // The census's answer to "what is the game holding right now", browsable
  // like a search result. Rows reuse the plain Row, so opening works as ever.
  const loadedEntries: DirEntry[] = liveLoaded.map((t) => ({
    name: `${t.short.split("/").pop() ?? t.short}.${t.group}`,
    path: t.short,
    kind: "tag" as const,
    index: t.index,
    size: 0,
    children: null,
  }));

  if (showLoaded && !searching && liveLoaded.length > 0) {
    return (
      <div className="flex min-h-0 flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-border-subtle px-3 py-2">
          <span className="font-mono text-[11px] text-text-dim">
            {liveLoaded.length} tag{liveLoaded.length === 1 ? "" : "s"} loaded in the running game
          </span>
          <button
            type="button"
            onClick={() => setShowLoaded(false)}
            className="font-mono text-[10px] uppercase tracking-wider text-text-dim hover:text-text-primary"
          >
            back
          </button>
        </div>
        <ul className="min-h-0 flex-1 overflow-y-auto">
          {loadedEntries.map((e) => (
            <Row key={`${e.kind}-${e.path}`} entry={e} showPath />
          ))}
        </ul>
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="border-b border-border-subtle p-3">
        <input
          type="search"
          value={fileQuery}
          onChange={(e) => void searchFiles(e.target.value)}
          placeholder="Search all assets…"
          className="w-full border border-border-subtle bg-surface-card px-3 py-2 text-sm outline-none placeholder:text-text-dim focus:border-mjolnir-gold"
        />
      </div>

      {searching ? (
        <div className="border-b border-border-subtle px-3 py-2 font-mono text-[11px] text-text-dim">
          {entries.length === 500 ? "first 500 matches" : `${entries.length} match${entries.length === 1 ? "" : "es"}`}
        </div>
      ) : (
        <div className="flex items-center border-b border-border-subtle">
          {dir !== "" && (
            <button
              type="button"
              onClick={() => void openDir(parent)}
              title="Up one level"
              className="shrink-0 px-2 py-2 font-mono text-xs text-text-dim hover:text-text-primary"
            >
              ↑
            </button>
          )}
          <div className="min-w-0 flex-1">
            <Breadcrumbs />
          </div>
          {liveLoaded.length > 0 && (
            <button
              type="button"
              onClick={() => setShowLoaded(true)}
              title="Only the tags the last game scan found loaded"
              className="shrink-0 px-2 py-1 font-mono text-[10px] uppercase tracking-wider text-accent-green hover:bg-surface-hover"
            >
              ● in game ({liveLoaded.length})
            </button>
          )}
        </div>
      )}

      <ul className="min-h-0 flex-1 overflow-y-auto">
        {entries.map((e) => (
          <Row key={`${e.kind}-${e.path}`} entry={e} showPath={searching} />
        ))}
        {entries.length === 0 &&
          (dirLoading ? (
            <li className="flex items-center gap-2 px-3 py-4 text-xs text-text-dim">
              <Spinner className="h-3 w-3" />
              {searching ? "Searching…" : "Reading…"}
            </li>
          ) : (
            <li className="px-3 py-4 text-xs text-text-dim">
              {searching ? "Nothing matched." : "Empty."}
            </li>
          ))}
      </ul>
    </div>
  );
}
