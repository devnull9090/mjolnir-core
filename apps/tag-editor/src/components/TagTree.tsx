import { tagLabel, useEditor } from "../stores/editor-store";
import { FileBrowser } from "./FileBrowser";
import { ModPanel } from "./ModPanel";

/** What each left-panel mode is for, since four tabs need distinguishing. */
const MODES = [
  { id: "files", label: "files", hint: "Browse every asset by path, like a file dialog" },
  { id: "tags", label: "groups", hint: "Browse tags by their Blam group" },
  { id: "textures", label: "textures", hint: "Browse texture assets only" },
  { id: "mod", label: "mod", hint: "Your mod: its changes, test install, export and publish" },
] as const;

/** Left panel: mode tabs, search, and the listing for the chosen mode. */
export function TagTree() {
  const { browse } = useEditor();
  const setBrowse = useEditor((s) => s.setBrowse);
  const project = useEditor((s) => s.project);

  return (
    <div className="flex h-full min-h-0 w-[22rem] shrink-0 flex-col border-r border-border-subtle">
      <div className="flex border-b border-border-subtle">
        {MODES.map((mode) => (
          <button
            key={mode.id}
            type="button"
            onClick={() => setBrowse(mode.id)}
            title={mode.hint}
            className={`flex-1 px-3 py-2 text-xs uppercase tracking-wider ${
              browse === mode.id
                ? "border-b-2 border-mjolnir-gold text-mjolnir-gold"
                : "text-text-dim hover:text-text-secondary"
            }`}
          >
            {mode.label}
            {mode.id === "mod" && project && (
              <span
                className="ml-1 inline-block h-1.5 w-1.5 rounded-full bg-mjolnir-gold align-middle"
                title={`${project.meta.name} is open`}
              />
            )}
          </button>
        ))}
      </div>
      {browse === "files" ? (
        <FileBrowser />
      ) : browse === "tags" ? (
        <TagList />
      ) : browse === "textures" ? (
        <TextureList />
      ) : (
        <ModPanel />
      )}
    </div>
  );
}

/** Group list and tag list. Search spans every group when a query is set. */
function TagList() {
  const { groups, selectedGroup, tags, query, selectedTag } = useEditor();
  const selectGroup = useEditor((s) => s.selectGroup);
  const openTab = useEditor((s) => s.openTab);
  const search = useEditor((s) => s.search);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="border-b border-border-subtle p-3">
        <input
          type="search"
          value={query}
          onChange={(e) => void search(e.target.value)}
          placeholder="Search tags…"
          className="w-full border border-border-subtle bg-surface-card px-3 py-2 text-sm outline-none placeholder:text-text-dim focus:border-mjolnir-gold"
        />
      </div>

      <div className="flex min-h-0 flex-1">
        <ul className="w-40 shrink-0 overflow-y-auto border-r border-border-subtle">
          {groups.map((g) => (
            <li key={g.group}>
              <button
                type="button"
                onClick={() => void selectGroup(g.group)}
                className={`flex w-full items-baseline justify-between px-3 py-1.5 text-left text-xs transition-colors hover:bg-surface-hover ${
                  selectedGroup === g.group
                    ? "bg-surface-card text-mjolnir-gold"
                    : "text-text-secondary"
                }`}
                title={`${g.group} (${g.four_cc})`}
              >
                <span className="truncate">{g.group}</span>
                <span className="ml-2 shrink-0 font-mono text-[10px] text-text-dim">
                  {g.count}
                </span>
              </button>
            </li>
          ))}
        </ul>

        <ul className="min-w-0 flex-1 overflow-y-auto">
          {tags.map((t) => {
            // The tag name is the tail of the path, so showing the head and
            // truncating the end makes every tag in a directory look alike.
            const cut = t.short.lastIndexOf("/");
            const dir = cut < 0 ? "" : t.short.slice(0, cut);
            const name = cut < 0 ? t.short : t.short.slice(cut + 1);
            return (
              <li key={t.index}>
                <button
                  type="button"
                  onClick={() => void openTab("tag", t.index, tagLabel(t))}
                  className={`flex w-full items-baseline px-3 py-1.5 text-left font-mono text-xs transition-colors hover:bg-surface-hover ${
                    selectedTag === t.index
                      ? "bg-surface-card text-mjolnir-gold"
                      : "text-text-secondary"
                  }`}
                  title={t.short}
                >
                  <span className="min-w-0 flex-1 truncate">{name}</span>
                  {dir && (
                    <span
                      className="ml-2 min-w-0 shrink truncate text-[10px] text-text-dim"
                      dir="rtl"
                    >
                      {dir}
                    </span>
                  )}
                  {query && (
                    <span className="ml-2 shrink-0 text-[10px] text-text-dim">
                      {t.group}
                    </span>
                  )}
                </button>
              </li>
            );
          })}
          {tags.length === 0 && (
            <li className="px-3 py-4 text-xs text-text-dim">
              {selectedGroup || query ? "No tags." : "Select a group."}
            </li>
          )}
        </ul>
      </div>
    </div>
  );
}

/** Texture asset list with search. */
function TextureList() {
  const { textures, textureQuery, selectedTexture } = useEditor();
  const searchTextures = useEditor((s) => s.searchTextures);
  const openTab = useEditor((s) => s.openTab);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="border-b border-border-subtle p-3">
        <input
          type="search"
          value={textureQuery}
          onChange={(e) => void searchTextures(e.target.value)}
          placeholder="Search textures…"
          className="w-full border border-border-subtle bg-surface-card px-3 py-2 text-sm outline-none placeholder:text-text-dim focus:border-mjolnir-gold"
        />
      </div>
      <ul className="min-h-0 flex-1 overflow-y-auto">
        {textures.map((t) => {
          const cut = t.path.lastIndexOf("/");
          const dir = cut < 0 ? "" : t.path.slice(0, cut);
          const name = cut < 0 ? t.path : t.path.slice(cut + 1);
          return (
            <li key={t.index}>
              <button
                type="button"
                onClick={() =>
                  void openTab("texture", t.index, t.path.split("/").pop() ?? t.path)
                }
                className={`flex w-full items-baseline px-3 py-1.5 text-left font-mono text-xs transition-colors hover:bg-surface-hover ${
                  selectedTexture === t.index
                    ? "bg-surface-card text-mjolnir-gold"
                    : "text-text-secondary"
                }`}
                title={t.path}
              >
                <span className="min-w-0 flex-1 truncate">{name}</span>
                {dir && (
                  <span
                    className="ml-2 min-w-0 shrink truncate text-[10px] text-text-dim"
                    dir="rtl"
                  >
                    {dir}
                  </span>
                )}
              </button>
            </li>
          );
        })}
        {textures.length === 0 && (
          <li className="px-3 py-4 text-xs text-text-dim">No textures found.</li>
        )}
      </ul>
    </div>
  );
}
