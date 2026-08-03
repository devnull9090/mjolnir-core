import { useEditor } from "../stores/editor-store";
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
  const tabs = useEditor((s) => s.tabs);

  const isDir = entry.kind === "dir";
  const open = isDir
    ? () => void openDir(entry.path)
    : () =>
        void openTab(
          entry.kind === "texture" ? "texture" : "tag",
          entry.index ?? 0,
          entry.name,
        );

  const isOpen =
    !isDir &&
    tabs.some(
      (t) => t.kind === (entry.kind === "texture" ? "texture" : "tag") && t.index === entry.index,
    );

  // In search results the name alone is ambiguous, so show where it lives.
  const parent = entry.path.slice(0, Math.max(0, entry.path.lastIndexOf("/")));

  return (
    <li>
      <button
        type="button"
        onDoubleClick={open}
        onClick={open}
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
                : "text-mjolnir-gold/70"
          }`}
        >
          {isDir ? "▸" : entry.kind === "texture" ? "▣" : "◆"}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate font-mono text-xs">{entry.name}</span>
          {showPath && parent && (
            <span className="block truncate font-mono text-[10px] text-text-dim">{parent}</span>
          )}
        </span>
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

  const searching = fileQuery.trim() !== "";
  const parent = dir.slice(0, Math.max(0, dir.lastIndexOf("/")));

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
