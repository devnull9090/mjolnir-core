import { useEffect, useState } from "react";
import { save } from "@tauri-apps/plugin-dialog";
import { MODEL_GROUPS, tagLabel, useEditor, type ViewMode } from "../stores/editor-store";
import { SoundPlayer } from "./SoundPlayer";

/** Links longer than this start collapsed, so a scenario's hundreds of
 *  imports do not take over the inspector. */
const LINKS_COLLAPSED_OVER = 24;

/** Chips for the packages this tag imports; openable ones open in a tab. */
function LinkedAssets() {
  const links = useEditor((s) => s.tagLinks);
  const openTab = useEditor((s) => s.openTab);
  const [showAll, setShowAll] = useState(false);
  const [open, setOpen] = useState<boolean | null>(null);

  if (links.length === 0) return null;
  const openable = links.filter((l) => l.index !== null);
  const rest = links.filter((l) => l.index === null);
  const shown = showAll ? links : openable;
  const expanded = open ?? links.length <= LINKS_COLLAPSED_OVER;

  return (
    <div className="mt-2">
      <button
        type="button"
        onClick={() => setOpen(!expanded)}
        className="font-mono text-[10px] uppercase tracking-wider text-text-dim hover:text-text-secondary"
        title={expanded ? "Collapse the linked packages" : "Show the linked packages"}
      >
        {expanded ? "▾" : "▸"} linked · {openable.length} openable
        {rest.length > 0 ? ` · ${rest.length} unreal` : ""}
      </button>
      {expanded && (
        <div className="mt-1 flex max-h-28 flex-wrap content-start items-center gap-1.5 overflow-y-auto pr-1">
          {shown.map((l) => (
            <button
              key={l.package}
              type="button"
              disabled={l.index === null}
              title={
                l.index === null
                  ? `${l.package}\n\nAn Unreal ${l.label.startsWith("BP_") ? "Blueprint" : "asset"}; the editor cannot open this kind yet.`
                  : l.package
              }
              onClick={() => {
                if (l.index !== null) {
                  void openTab(l.kind === "texture" ? "texture" : "tag", l.index, l.label);
                }
              }}
              className={`border px-1.5 py-0.5 font-mono text-[10px] ${
                l.index === null
                  ? "cursor-default border-border-subtle/60 text-text-dim"
                  : l.kind === "texture"
                    ? "border-accent-blue/40 text-accent-blue hover:bg-accent-blue/10"
                    : "border-mjolnir-gold/40 text-mjolnir-gold hover:bg-mjolnir-gold/10"
              }`}
            >
              {l.label}
            </button>
          ))}
          {rest.length > 0 && (
            <button
              type="button"
              onClick={() => setShowAll((v) => !v)}
              className="font-mono text-[10px] text-text-dim hover:text-text-secondary"
            >
              {showAll ? "hide unreal" : `+${rest.length} unreal`}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * "What references this tag?" — collapsed until asked, because the answer
 * costs a one-time scan of every shipped tag (see `referencing_tags`). The
 * chips share the linked-assets grammar; each opens the referencing tag.
 */
function ReferencedBy() {
  const selectedTag = useEditor((s) => s.selectedTag);
  const rows = useEditor((s) => s.reverseRefs);
  const loading = useEditor((s) => s.reverseRefsLoading);
  const error = useEditor((s) => s.reverseRefsError);
  const load = useEditor((s) => s.loadReverseRefs);
  const openTab = useEditor((s) => s.openTab);
  const [open, setOpen] = useState(false);

  // Collapse again when another tag takes the pane.
  useEffect(() => setOpen(false), [selectedTag]);

  return (
    <div className="mt-1">
      <button
        type="button"
        onClick={() => {
          setOpen((v) => !v);
          if (!open && rows === null && !loading) void load();
        }}
        className="font-mono text-[10px] uppercase tracking-wider text-text-dim hover:text-text-secondary"
        title="Every tag whose fields reference this one"
      >
        {open ? "▾" : "▸"} referenced by{rows ? ` · ${rows.length}` : ""}
      </button>
      {open && (
        <div className="mt-1 flex max-h-28 flex-wrap content-start items-center gap-1.5 overflow-y-auto pr-1">
          {loading && (
            <span className="font-mono text-[10px] text-text-dim">
              scanning every tag for references — up to a minute, once per game version…
            </span>
          )}
          {error && <span className="font-mono text-[10px] text-accent-red">{error}</span>}
          {rows?.length === 0 && (
            <span className="font-mono text-[10px] text-text-dim">
              nothing references this tag
            </span>
          )}
          {rows?.map((t) => (
            <button
              key={t.index}
              type="button"
              title={t.short}
              onClick={() =>
                void openTab("tag", t.index, tagLabel(t), { group: t.group, path: t.short })
              }
              className="border border-mjolnir-gold/40 px-1.5 py-0.5 font-mono text-[10px] text-mjolnir-gold hover:bg-mjolnir-gold/10"
            >
              {tagLabel(t)}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/** A byte count as the short label a chip has room for. */
function shortBytes(n: number | null): string {
  if (n === null) return "";
  if (n >= 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  if (n >= 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${n} B`;
}

/**
 * What the open sound tag actually plays.
 *
 * The Blam permutations in the form are legacy metadata; the audio itself is
 * on the Wwise side, reached through the tag's event packages and the bank
 * graph (see `wwise_audio_for_tag`). Wwise ships variation names as hashes,
 * so the chips are numbered rather than named — but every one is playable,
 * including media that exists only inside a bank. Collapsed until asked,
 * because answering costs package reads and a bank parse.
 */
function TagAudioSection() {
  const tag = useEditor((s) => s.tag);
  const selectedTag = useEditor((s) => s.selectedTag);
  const audio = useEditor((s) => s.tagAudio);
  const loading = useEditor((s) => s.tagAudioLoading);
  const error = useEditor((s) => s.tagAudioError);
  const load = useEditor((s) => s.loadTagAudio);
  const [open, setOpen] = useState(false);
  const [picked, setPicked] = useState(0);

  // Collapse and forget the pick when another tag takes the pane.
  useEffect(() => {
    setOpen(false);
    setPicked(0);
  }, [selectedTag]);

  if (!tag || !tag.group.startsWith("sound")) return null;

  const media = audio?.media ?? [];
  const hit = media[Math.min(picked, Math.max(media.length - 1, 0))] ?? null;
  return (
    <div className="mt-1">
      <button
        type="button"
        onClick={() => {
          setOpen((v) => !v);
          if (!open && audio === null && !loading) void load();
        }}
        className="font-mono text-[10px] uppercase tracking-wider text-text-dim hover:text-text-secondary"
        title="The Wwise audio this tag's events play, every variation playable — including media embedded in sound banks"
      >
        {open ? "▾" : "▸"} audio
        {audio
          ? ` · ${media.length} variation${media.length === 1 ? "" : "s"}`
          : ""}
      </button>
      {open && (
        <div className="mt-1">
          {loading && (
            <span className="font-mono text-[10px] text-text-dim">
              walking the event packages and their banks…
            </span>
          )}
          {error && <span className="font-mono text-[10px] text-accent-red">{error}</span>}
          {audio && media.length === 0 && (
            <span className="font-mono text-[10px] text-text-dim">
              {audio.events.length > 0
                ? `${audio.events.join(", ")} reaches no media in this installation`
                : "no Wwise events are linked to this tag"}
            </span>
          )}
          {audio && audio.events.length > 0 && media.length > 0 && (
            <p className="mb-1 font-mono text-[10px] text-text-dim">
              {audio.events.join(" · ")}
            </p>
          )}
          {media.length > 1 && (
            <div className="mb-1 flex max-h-20 flex-wrap content-start items-center gap-1.5 overflow-y-auto pr-1">
              {media.map((m, i) => (
                <button
                  key={m.id}
                  type="button"
                  onClick={() => setPicked(i)}
                  title={`${m.event || "media"} · ${m.id}${
                    m.bank !== null ? " · embedded in a sound bank" : ""
                  }${m.size !== null ? ` · ${m.size.toLocaleString()} bytes` : ""}`}
                  aria-pressed={i === picked}
                  className={`border px-1.5 py-0.5 font-mono text-[10px] ${
                    i === picked
                      ? "border-mjolnir-gold bg-mjolnir-gold/10 text-mjolnir-gold"
                      : "border-border-subtle text-text-secondary hover:bg-surface-hover"
                  }`}
                >
                  {i + 1}
                  {m.bank !== null ? "·bnk" : ""}
                  {m.size !== null ? ` ${shortBytes(m.size)}` : ""}
                </button>
              ))}
            </div>
          )}
          {hit &&
            (hit.sound !== null ? (
              <SoundPlayer index={hit.sound} />
            ) : hit.bank !== null ? (
              <SoundPlayer bank={hit.bank} media={hit.id} />
            ) : null)}
        </div>
      )}
    </div>
  );
}

/** Header shared by both inspector views: identity, vitals, view toggle. */
/**
 * Live mode: mirror each accepted edit into the running game.
 *
 * Deliberately a toggle rather than something implied by the game being open.
 * It writes into another process's memory, and it is not persistence — the
 * mod project is still the record of what the edit is. Off on every launch.
 */
function LiveToggle() {
  const live = useEditor((s) => s.live);
  const liveOn = useEditor((s) => s.liveOn);
  const poking = useEditor((s) => s.livePoking);
  const scanning = useEditor((s) => s.liveScanning);
  const note = useEditor((s) => s.liveNote);
  const setLiveOn = useEditor((s) => s.setLiveOn);
  const refreshLive = useEditor((s) => s.refreshLive);
  const censusLive = useEditor((s) => s.censusLive);

  // Poll only while armed: the check attaches to the process, and doing that
  // every few seconds for a feature nobody switched on is rude.
  useEffect(() => {
    if (!liveOn) return;
    void refreshLive();
    const t = setInterval(() => void refreshLive(), 5000);
    return () => clearInterval(t);
  }, [liveOn, refreshLive]);

  const running = live?.running ?? false;
  return (
    <div className="mt-2 flex flex-wrap items-center gap-2">
      <button
        type="button"
        onClick={() => setLiveOn(!liveOn)}
        title={
          "Push each edit into the running game as well as the project.\n\n" +
          "Scan the game once and every loaded tag is found at the same time, " +
          "so edits to them are instant; without a scan the first edit to a tag " +
          "pays for its own search. Fixed-width fields only — anything that " +
          "resizes the tag still needs a rebuild.\n\n" +
          "Nothing is written to disk, so a live change is gone at the next launch."
        }
        className={`border px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider ${
          liveOn
            ? "border-accent-green/60 bg-accent-green/10 text-accent-green"
            : "border-border-subtle text-text-dim hover:bg-surface-hover"
        }`}
      >
        live {liveOn ? "on" : "off"}
      </button>
      {liveOn && running && (
        <button
          type="button"
          disabled={scanning}
          onClick={() => void censusLive()}
          title={
            "Sweep the game's memory once and find every loaded tag at its " +
            "address — including which level is loaded. Takes tens of seconds; " +
            "afterwards every found tag edits instantly."
          }
          className="border border-border-subtle px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-text-dim enabled:hover:bg-surface-hover disabled:opacity-50"
        >
          {scanning ? "scanning…" : "scan game"}
        </button>
      )}
      {liveOn && (
        <span className="font-mono text-[10px] text-text-dim">
          {poking
            ? "writing…"
            : running
              ? `game running · pid ${live?.pid}` +
                (live?.level ? ` · in ${live.level}` : "") +
                ` · ${live?.located ?? 0} located` +
                ((live?.present ?? 0) > 0 ? ` · ${live?.present} present` : "")
              : "no game running — edits are recorded but not pushed"}
        </span>
      )}
      {liveOn && note && (
        <span
          className={`font-mono text-[10px] ${
            note.startsWith("live: Error") || note.includes("cannot") || note.includes("not")
              ? "text-accent-red"
              : "text-accent-green"
          }`}
        >
          {note}
        </span>
      )}
    </div>
  );
}

export function TagHeader() {
  const { tag, viewMode } = useEditor();
  const setViewMode = useEditor((s) => s.setViewMode);
  const degrees = useEditor((s) => s.degrees);
  const setDegrees = useEditor((s) => s.setDegrees);

  if (!tag) return null;
  // Only a scenario carries Blam script, so the third view is offered only
  // where there is something for it to show.
  const modes: { mode: ViewMode; label: string; title: string }[] = [
    {
      mode: "form",
      label: "Form",
      title: "Guerilla-style form: section bars, element dropdowns, typed controls",
    },
    { mode: "tree", label: "Tree", title: "Flat tree of every field with offsets and types" },
    ...(tag.group === "scenario"
      ? [
          {
            mode: "script" as ViewMode,
            label: "Script",
            title: "The mission's Blam script, as the scenario shipped it",
          },
          {
            mode: "world" as ViewMode,
            label: "World",
            title:
              "The level in 3D: collision world, placements, squads and volumes — select and move things",
          },
        ]
      : []),
    ...(MODEL_GROUPS.includes(tag.group)
      ? [
          {
            mode: "model" as ViewMode,
            label: "Model",
            title:
              "3D view of the simulation geometry: collision shell, skeleton and markers",
          },
        ]
      : []),
  ];

  return (
    <header className="sticky top-0 z-10 border-b border-border-subtle bg-surface-primary px-6 py-4">
      <div className="flex flex-wrap items-baseline gap-3">
        <h1 className="font-mono text-lg text-mjolnir-gold">{tag.group}</h1>
        <span className="font-mono text-xs text-text-dim">{tag.four_cc}</span>
        <span className="font-mono text-xs text-text-dim">v{tag.version}</span>
        <div className="ml-auto flex">
          {modes.map((m) => (
            <button
              key={m.mode}
              type="button"
              onClick={() => setViewMode(m.mode)}
              title={m.title}
              aria-pressed={viewMode === m.mode}
              className={`border border-border-subtle px-2 py-0.5 text-[11px] ${
                viewMode === m.mode
                  ? "bg-surface-hover text-mjolnir-gold"
                  : "text-text-secondary hover:bg-surface-hover"
              }`}
            >
              {m.label}
            </button>
          ))}
          <button
            type="button"
            onClick={() => setDegrees(!degrees)}
            aria-pressed={degrees}
            title={
              degrees
                ? "Angles are shown and typed in degrees; the tag stores radians. Click for radians."
                : "Angles are shown as stored, in radians. Click to show and type them in degrees."
            }
            className={`ml-2 border border-border-subtle px-2 py-0.5 font-mono text-[11px] ${
              degrees
                ? "bg-surface-hover text-mjolnir-gold"
                : "text-text-secondary hover:bg-surface-hover"
            }`}
          >
            {degrees ? "deg" : "rad"}
          </button>
        </div>
        <span
          className={`font-mono text-[11px] ${
            tag.data_exact ? "text-accent-green" : "text-text-dim"
          }`}
          title={
            tag.data_exact
              ? "The value walk consumed the data payload exactly."
              : "The values shown may be incomplete."
          }
        >
          {tag.data_exact ? "values exact" : "values partial"}
        </span>
      </div>
      <p className="mt-1 truncate font-mono text-[11px] text-text-secondary">{tag.path}</p>
      <p className="mt-1 font-mono text-[11px] text-text-dim">
        {tag.chunk_size.toLocaleString()} bytes · {tag.data_size.toLocaleString()} bytes of data ·{" "}
        {tag.node_count.toLocaleString()} fields
      </p>
      <LinkedAssets />
      <ReferencedBy />
      <TagAudioSection />
      <LiveToggle />
    </header>
  );
}

/** Pending edits: saved into the mod project when one is open, exportable
 *  either way. */
export function EditBar() {
  const { tag, lastEdit, editError } = useEditor();
  const project = useEditor((s) => s.project);
  const setBrowse = useEditor((s) => s.setBrowse);
  const revertTag = useEditor((s) => s.revertTag);
  const undoEdit = useEditor((s) => s.undoEdit);
  const redoEdit = useEditor((s) => s.redoEdit);
  const exportTag = useEditor((s) => s.exportTag);
  const [wrote, setWrote] = useState<string | null>(null);

  useEffect(() => setWrote(null), [tag?.path]);

  if (!tag) return null;
  const count = tag.edited.length;
  const history = tag.history ?? { undo: 0, redo: 0 };
  // The bar stays while something can be redone: undoing every edit must not
  // hide the way back.
  if (count === 0 && !editError && history.redo === 0) return null;

  async function onExport() {
    if (!tag) return;
    const name = tag.path.split("/").pop() ?? "tag.ubulk";
    const dest = await save({ defaultPath: name });
    if (!dest) return;
    const written = await exportTag(dest);
    if (written !== null) setWrote(`${written.toLocaleString()} bytes to ${dest}`);
  }

  return (
    <div className="border-b border-mjolnir-gold/40 bg-mjolnir-gold/5 px-6 py-2">
      <div className="flex flex-wrap items-center gap-3 text-xs">
        <span className="text-mjolnir-gold">
          {count} edit{count === 1 ? "" : "s"}
          {project ? ` in ${project.meta.name}` : " (not in a mod)"}
        </span>
        <button
          type="button"
          onClick={() => void onExport()}
          disabled={count === 0}
          className="border border-mjolnir-gold/60 px-2 py-0.5 text-mjolnir-gold hover:bg-mjolnir-gold/10 disabled:opacity-40"
        >
          Export patched tag…
        </button>
        <button
          type="button"
          onClick={() => void revertTag()}
          disabled={count === 0}
          className="border border-border-subtle px-2 py-0.5 text-text-secondary hover:bg-surface-hover disabled:opacity-40"
        >
          Revert all
        </button>
        <span className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => void undoEdit()}
            disabled={history.undo === 0}
            title={`Undo the last change to this tag (Ctrl+Z) — ${history.undo} step${
              history.undo === 1 ? "" : "s"
            } back`}
            className="border border-border-subtle px-2 py-0.5 font-mono text-text-secondary hover:bg-surface-hover disabled:opacity-40"
          >
            ↶ {history.undo}
          </button>
          <button
            type="button"
            onClick={() => void redoEdit()}
            disabled={history.redo === 0}
            title={`Redo (Ctrl+Y) — ${history.redo} step${history.redo === 1 ? "" : "s"} forward`}
            className="border border-border-subtle px-2 py-0.5 font-mono text-text-secondary hover:bg-surface-hover disabled:opacity-40"
          >
            ↷ {history.redo}
          </button>
        </span>
        {project ? (
          <button
            type="button"
            onClick={() => setBrowse("mod")}
            className="ml-auto font-mono text-[10px] text-text-dim hover:text-mjolnir-gold"
            title="Saved to the project on every edit. Open the mod panel to test, export or publish."
          >
            autosaved — open mod panel →
          </button>
        ) : (
          <button
            type="button"
            onClick={() => setBrowse("mod")}
            className="ml-auto font-mono text-[10px] text-text-dim hover:text-mjolnir-gold"
            title="Edits live in memory until they are part of a mod. Start one to keep them."
          >
            start a mod to keep these →
          </button>
        )}
      </div>
      {lastEdit && (
        <p className="mt-1 font-mono text-[10px] text-text-secondary">
          {lastEdit.path}: {lastEdit.before} → {lastEdit.after} ({lastEdit.changed_bytes}{" "}
          byte{lastEdit.changed_bytes === 1 ? "" : "s"} changed)
        </p>
      )}
      {editError && (
        <p className="mt-1 font-mono text-[10px] text-accent-red">{editError}</p>
      )}
      {wrote && <p className="mt-1 font-mono text-[10px] text-accent-green">Wrote {wrote}</p>}
    </div>
  );
}
