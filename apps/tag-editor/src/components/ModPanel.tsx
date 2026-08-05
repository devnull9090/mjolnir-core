import { useState } from "react";
import { open as openDialog } from "@tauri-apps/plugin-dialog";
import { openUrl } from "@tauri-apps/plugin-opener";
import { useEditor } from "../stores/editor-store";
import { isTauri } from "../lib/mock";
import type { HubStatus, ProjectMeta, TagChange, TextureChange } from "../lib/api";

/** Folder picker; outside Tauri (browser dev against the mock) any string
 *  keeps the flow walkable. */
async function pickFolder(title: string): Promise<string | null> {
  if (!isTauri) return "(mock)";
  const dir = await openDialog({ directory: true, title });
  return typeof dir === "string" ? dir : null;
}

/** The mod panel: the project's identity, its change list, and the path from
 *  "I edited a tag" to "it is on the hub". */
export function ModPanel() {
  const project = useEditor((s) => s.project);
  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
      {project ? <ProjectPanel /> : <StartPanel />}
    </div>
  );
}

function slugify(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 64);
}

function formatSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MiB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KiB`;
}

const inputClass =
  "w-full border border-border-subtle bg-surface-card px-2 py-1.5 text-xs outline-none placeholder:text-text-dim focus:border-mjolnir-gold";
const buttonGold =
  "border border-mjolnir-gold/60 px-2 py-1 text-xs text-mjolnir-gold hover:bg-mjolnir-gold/10 disabled:opacity-40";
const buttonPlain =
  "border border-border-subtle px-2 py-1 text-xs text-text-secondary hover:bg-surface-hover disabled:opacity-40";

/** No project yet: explain the model, then create or open one. */
function StartPanel() {
  const projectError = useEditor((s) => s.projectError);
  const newProject = useEditor((s) => s.newProject);
  const openProject = useEditor((s) => s.openProject);
  const tag = useEditor((s) => s.tag);

  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [slugTouched, setSlugTouched] = useState(false);
  const [summary, setSummary] = useState("");

  async function onCreate() {
    const dir = await pickFolder("Choose an empty folder for the mod project");
    if (dir === null) return;
    const ok = await newProject(dir, name.trim(), slug, "0.1.0", summary);
    if (ok) setCreating(false);
  }

  async function onOpen() {
    const dir = await pickFolder("Open a mod project folder");
    if (dir === null) return;
    await openProject(dir);
  }

  return (
    <div className="flex flex-col gap-3 p-3 text-xs text-text-secondary">
      <p>
        A mod is a saved recipe of edits: which tags change, and what they
        become. It lives in a folder of yours, autosaves as you edit, and can
        be tested in game, exported, and published to the hub from here.
      </p>
      {tag && !creating && (
        <p className="text-text-dim">
          Edits you have already made carry over into a new mod.
        </p>
      )}
      {creating ? (
        <div className="flex flex-col gap-2">
          <label className="flex flex-col gap-1">
            <span className="text-[10px] uppercase tracking-wider text-text-dim">Name</span>
            <input
              className={inputClass}
              value={name}
              autoFocus
              placeholder="Faster Pistol"
              onChange={(e) => {
                setName(e.target.value);
                if (!slugTouched) setSlug(slugify(e.target.value));
              }}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[10px] uppercase tracking-wider text-text-dim">
              Slug (its address on the hub)
            </span>
            <input
              className={inputClass}
              value={slug}
              placeholder="faster-pistol"
              onChange={(e) => {
                setSlugTouched(true);
                setSlug(e.target.value);
              }}
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[10px] uppercase tracking-wider text-text-dim">
              Summary (optional)
            </span>
            <input
              className={inputClass}
              value={summary}
              placeholder="One line about what it does"
              onChange={(e) => setSummary(e.target.value)}
            />
          </label>
          <div className="flex gap-2">
            <button
              type="button"
              className={buttonGold}
              disabled={!name.trim() || !slug}
              onClick={() => void onCreate()}
            >
              Choose folder & create
            </button>
            <button type="button" className={buttonPlain} onClick={() => setCreating(false)}>
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="flex gap-2">
          <button type="button" className={buttonGold} onClick={() => setCreating(true)}>
            New mod…
          </button>
          <button type="button" className={buttonPlain} onClick={() => void onOpen()}>
            Open mod…
          </button>
        </div>
      )}
      {projectError && <p className="font-mono text-[11px] text-accent-red">{projectError}</p>}
    </div>
  );
}

/** Identity fields, saved explicitly so half-typed versions never hit disk. */
function MetaForm({ meta }: { meta: ProjectMeta }) {
  const saveProjectMeta = useEditor((s) => s.saveProjectMeta);
  const [name, setName] = useState(meta.name);
  const [slug, setSlug] = useState(meta.slug);
  const [version, setVersion] = useState(meta.version);
  const [summary, setSummary] = useState(meta.summary);
  const dirty =
    name !== meta.name || slug !== meta.slug || version !== meta.version || summary !== meta.summary;

  return (
    <div className="flex flex-col gap-2 border-b border-border-subtle p-3">
      <div className="flex gap-2">
        <label className="flex min-w-0 flex-1 flex-col gap-1">
          <span className="text-[10px] uppercase tracking-wider text-text-dim">Name</span>
          <input className={inputClass} value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="flex w-20 shrink-0 flex-col gap-1">
          <span className="text-[10px] uppercase tracking-wider text-text-dim">Version</span>
          <input
            className={inputClass}
            value={version}
            onChange={(e) => setVersion(e.target.value)}
          />
        </label>
      </div>
      <label className="flex flex-col gap-1">
        <span className="text-[10px] uppercase tracking-wider text-text-dim">Slug</span>
        <input className={inputClass} value={slug} onChange={(e) => setSlug(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1">
        <span className="text-[10px] uppercase tracking-wider text-text-dim">Summary</span>
        <input className={inputClass} value={summary} onChange={(e) => setSummary(e.target.value)} />
      </label>
      {dirty && (
        <button
          type="button"
          className={buttonGold}
          onClick={() => void saveProjectMeta(name.trim(), slug, version.trim(), summary)}
        >
          Save details
        </button>
      )}
    </div>
  );
}

/** One tag's edits: open the tag, revert a line, or drop the lot. */
/** One replaced texture in the change list. */
function TextureRow({ change }: { change: TextureChange }) {
  const openTab = useEditor((s) => s.openTab);
  const label = change.path.split("/").pop() ?? change.path;
  const stale = change.index === null;

  return (
    <div className="flex items-baseline gap-2 border-b border-border-subtle/60 px-3 py-2">
      <button
        type="button"
        disabled={stale}
        title={change.path}
        onClick={() => {
          if (change.index !== null) void openTab("texture", change.index, label);
        }}
        className={`min-w-0 truncate font-mono text-xs ${
          stale ? "cursor-default text-text-dim" : "text-mjolnir-gold hover:underline"
        }`}
      >
        {label}
      </button>
      {stale && (
        <span
          className="shrink-0 text-[10px] text-accent-red"
          title="This texture is not in the open installation — the game may have updated. Revert the swap, or fix the recipe by hand."
        >
          missing
        </span>
      )}
      <span className="ml-auto shrink-0 font-mono text-[10px] text-text-dim">
        {Math.round(change.bytes / 1024).toLocaleString()} KB
      </span>
    </div>
  );
}

function ChangeRow({ change }: { change: TagChange }) {
  const openTab = useEditor((s) => s.openTab);
  const revertProjectEdit = useEditor((s) => s.revertProjectEdit);
  const label = `${change.tag.split("/").pop() ?? change.tag}.${change.group}`;
  const stale = change.index === null;

  return (
    <div className="border-b border-border-subtle/60 px-3 py-2">
      <div className="flex items-baseline gap-2">
        <button
          type="button"
          disabled={stale}
          title={`${change.tag}.${change.group}`}
          onClick={() => {
            if (change.index !== null) void openTab("tag", change.index, label);
          }}
          className={`min-w-0 truncate font-mono text-xs ${
            stale ? "cursor-default text-text-dim" : "text-mjolnir-gold hover:underline"
          }`}
        >
          {label}
        </button>
        {stale && (
          <span
            className="shrink-0 text-[10px] text-accent-red"
            title="This tag is not in the open installation — the game may have updated. Revert the edit, or fix the recipe by hand."
          >
            missing
          </span>
        )}
        <button
          type="button"
          onClick={() => void revertProjectEdit(change.group, change.tag, null)}
          title="Revert every edit to this tag"
          className="ml-auto shrink-0 text-[10px] text-text-dim hover:text-accent-red"
        >
          revert all
        </button>
      </div>
      <ul className="mt-1 flex flex-col gap-0.5">
        {change.edits.map((e) => (
          <li key={e.field} className="flex items-baseline gap-2 font-mono text-[11px]">
            <span className="min-w-0 flex-1 truncate text-text-secondary" title={e.field}>
              {e.field}
            </span>
            <span className="shrink-0 text-text-dim" title={e.before ?? undefined}>
              {e.before !== null && <>{e.before} → </>}
              <span className={e.stale ? "text-accent-red" : "text-mjolnir-gold"}>{e.value}</span>
            </span>
            <button
              type="button"
              onClick={() => void revertProjectEdit(change.group, change.tag, e.field)}
              title="Revert this edit"
              className="shrink-0 text-text-dim hover:text-accent-red"
            >
              ×
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** The device signing key, so "who bundled this" is visible before publish. */
function SigningLine() {
  const signing = useEditor((s) => s.signing);
  if (!signing?.fingerprint) return null;
  return (
    <p
      className="font-mono text-[10px] text-text-dim"
      title="Every archive this device exports is signed with its own key, so the hub and other players can prove who bundled it and that nothing changed the bytes."
    >
      signing key {signing.fingerprint.slice(0, 16)}… ({signing.label})
      {signing.registered === true && <span className="text-accent-green"> · registered</span>}
      {signing.registered === false && (
        <span> · registers on first publish</span>
      )}
    </p>
  );
}

/**
 * Not linked yet: pair with a hub account the way the launcher does.
 *
 * The editor asks the hub for a short code, the user approves it in a real
 * browser while signed in, and the key arrives here without ever being seen
 * or typed. Pasting a hand-minted key still works and is kept behind a
 * disclosure — it is the path for CI and for anyone who would rather choose
 * the scopes themselves, not the one to lead with.
 */
function LinkSection({ hub }: { hub: HubStatus }) {
  const link = useEditor((s) => s.link);
  const startHubLink = useEditor((s) => s.startHubLink);
  const cancelHubLink = useEditor((s) => s.cancelHubLink);
  const setHubKey = useEditor((s) => s.setHubKey);
  const [key, setKey] = useState("");
  const [pasting, setPasting] = useState(false);

  async function onLink() {
    const started = await startHubLink();
    // The code is on screen either way, so a browser that refuses to open
    // leaves the user inconvenienced rather than stuck.
    if (started) void openUrl(started.verification_url);
  }

  if (link?.status === "pending") {
    return (
      <>
        <p className="text-[11px] text-text-secondary">
          Approve this code on mjolnircore.com, signed in. Waiting…
        </p>
        <p className="font-mono text-lg tracking-widest text-mjolnir-gold">{link.user_code}</p>
        <div className="flex items-center gap-2">
          <button
            type="button"
            className={buttonPlain}
            onClick={() => void openUrl(link.verification_url)}
          >
            Open the page again
          </button>
          <button
            type="button"
            className="text-[10px] text-text-dim hover:text-text-secondary"
            onClick={cancelHubLink}
          >
            cancel
          </button>
        </div>
      </>
    );
  }

  return (
    <>
      {link ? (
        <p className="text-[11px] text-accent-red">
          {link.status === "denied"
            ? "That link was denied."
            : "That code expired before it was approved."}
        </p>
      ) : (
        <p className="text-[11px] text-text-secondary">
          Publishing needs a hub account. Linking opens mjolnircore.com, where you approve a short
          code — the editor never sees your password, and the key it gets can publish and nothing
          else. It is stored on this machine only.
        </p>
      )}
      <div className="flex items-center gap-2">
        <button type="button" className={buttonGold} onClick={() => void onLink()}>
          {link ? "Try again" : "Link hub account"}
        </button>
        <button
          type="button"
          className="text-[10px] text-text-dim hover:text-text-secondary"
          onClick={() => setPasting((p) => !p)}
        >
          {pasting ? "never mind" : "paste a key instead"}
        </button>
      </div>
      {pasting && (
        <>
          <p className="text-[11px] text-text-dim">
            Needs the <code>mods:write</code> scope.{" "}
            <button
              type="button"
              className="text-mjolnir-gold hover:underline"
              onClick={() => void openUrl(`${hub.base}/account/keys`)}
            >
              Create one on your hub account page
            </button>
            .
          </p>
          <div className="flex gap-2">
            <input
              type="password"
              className={inputClass}
              value={key}
              placeholder="mjc_…"
              onChange={(e) => setKey(e.target.value)}
            />
            <button
              type="button"
              className={buttonPlain}
              disabled={!key.trim()}
              onClick={() => {
                void setHubKey(key).then((ok) => ok && setKey(""));
              }}
            >
              Save
            </button>
          </div>
        </>
      )}
    </>
  );
}

/** Linking, changelog and the publish button with its verdict. */
function PublishSection() {
  const hub = useEditor((s) => s.hub);
  const project = useEditor((s) => s.project);
  const projectBusy = useEditor((s) => s.projectBusy);
  const publishResult = useEditor((s) => s.publishResult);
  const publishMod = useEditor((s) => s.publishMod);
  const unlinkHub = useEditor((s) => s.unlinkHub);
  const [changelog, setChangelog] = useState("");
  const hasChanges = (project?.changes.length ?? 0) > 0;

  return (
    <div className="flex flex-col gap-2 p-3">
      <h2 className="text-[10px] uppercase tracking-wider text-text-dim">Publish to the hub</h2>
      <SigningLine />
      {hub && !hub.has_key ? (
        <LinkSection hub={hub} />
      ) : (
        <>
          {hub?.username && (
            <p className="text-[10px] text-text-dim">
              linked as <span className="text-text-secondary">{hub.username}</span>
            </p>
          )}
          <textarea
            className={`${inputClass} min-h-14 resize-y`}
            value={changelog}
            placeholder="Changelog for this version (optional, Markdown)"
            onChange={(e) => setChangelog(e.target.value)}
          />
          <div className="flex items-center gap-2">
            <button
              type="button"
              className={buttonGold}
              disabled={projectBusy !== null || !hasChanges}
              onClick={() => void publishMod(changelog)}
            >
              {projectBusy === "publish"
                ? "Publishing…"
                : `Publish ${project?.meta.version ?? ""}`}
            </button>
            {hub && (
              <button
                type="button"
                className="text-[10px] text-text-dim hover:text-text-secondary"
                title="Forget the key stored here. It stays valid until you revoke it on the hub."
                onClick={() => void unlinkHub()}
              >
                unlink
              </button>
            )}
          </div>
        </>
      )}
      {publishResult && (
        <div className="flex flex-col gap-1 border border-border-subtle p-2">
          <p
            className={`text-xs ${
              publishResult.status === "published" ? "text-accent-green" : "text-accent-red"
            }`}
          >
            {publishResult.status === "published"
              ? `Published ${publishResult.version}.`
              : `The hub ${publishResult.status} this release.`}
          </p>
          {publishResult.findings.map((f, i) => (
            <p
              key={i}
              className={`font-mono text-[10px] ${
                f.level === "error" ? "text-accent-red" : "text-text-dim"
              }`}
            >
              {f.level} · {f.code}: {f.message}
            </p>
          ))}
          <button
            type="button"
            className="self-start text-[11px] text-mjolnir-gold hover:underline"
            onClick={() => void openUrl(publishResult.url)}
          >
            View on the hub →
          </button>
        </div>
      )}
    </div>
  );
}

function ProjectPanel() {
  const project = useEditor((s) => s.project)!;
  const projectError = useEditor((s) => s.projectError);
  const projectBusy = useEditor((s) => s.projectBusy);
  const exportResult = useEditor((s) => s.exportResult);
  const testResult = useEditor((s) => s.testResult);
  const closeProject = useEditor((s) => s.closeProject);
  const exportMod = useEditor((s) => s.exportMod);
  const testMod = useEditor((s) => s.testMod);
  const untestMod = useEditor((s) => s.untestMod);

  // A mod that only repaints a texture still has something to bake, so the
  // test and export buttons key off both lists.
  const hasChanges = project.changes.length > 0 || project.textures.length > 0;
  const tested = project.test_files.length > 0;
  const editCount = project.changes.reduce((n, c) => n + c.edits.length, 0);
  const swapCount = project.textures.length;

  return (
    <>
      <div className="flex items-baseline gap-2 border-b border-border-subtle px-3 py-2">
        <span className="min-w-0 truncate text-xs text-mjolnir-gold" title={project.root}>
          {project.meta.name}
        </span>
        <span className="shrink-0 font-mono text-[10px] text-text-dim">
          v{project.meta.version}
        </span>
        <button
          type="button"
          className="ml-auto shrink-0 text-[10px] text-text-dim hover:text-text-secondary"
          title={`Close the project. Everything is saved in ${project.root}.`}
          onClick={() => void closeProject()}
        >
          close
        </button>
      </div>

      {projectError && (
        <p className="border-b border-accent-red/40 bg-accent-red/5 px-3 py-2 font-mono text-[11px] text-accent-red">
          {projectError}
        </p>
      )}

      <MetaForm key={`${project.root}:${JSON.stringify(project.meta)}`} meta={project.meta} />

      <div className="border-b border-border-subtle">
        <h2 className="px-3 pt-2 text-[10px] uppercase tracking-wider text-text-dim">
          Changes · {editCount} edit{editCount === 1 ? "" : "s"} in {project.changes.length} tag
          {project.changes.length === 1 ? "" : "s"}
          {swapCount > 0 &&
            ` · ${swapCount} texture${swapCount === 1 ? "" : "s"}`}
        </h2>
        {hasChanges ? (
          <>
            {project.changes.map((c) => (
              <ChangeRow key={`${c.group}:${c.tag}`} change={c} />
            ))}
            {project.textures.map((t) => (
              <TextureRow key={t.path} change={t} />
            ))}
          </>
        ) : (
          <p className="px-3 py-2 text-[11px] text-text-dim">
            No changes yet. Open a tag and edit a field, or replace a texture —
            it lands here automatically.
          </p>
        )}
      </div>

      <div className="flex flex-col gap-2 border-b border-border-subtle p-3">
        <h2 className="text-[10px] uppercase tracking-wider text-text-dim">Try it</h2>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className={buttonGold}
            disabled={projectBusy !== null || !hasChanges}
            title="Bake the mod and install it into your Paks folder. Launch the game to see it; remove it here afterwards."
            onClick={() => void testMod()}
          >
            {projectBusy === "test" ? "Installing…" : tested ? "Update test install" : "Test in game"}
          </button>
          {tested && (
            <button
              type="button"
              className={buttonPlain}
              disabled={projectBusy !== null}
              onClick={() => void untestMod()}
            >
              {projectBusy === "untest" ? "Removing…" : "Remove test install"}
            </button>
          )}
        </div>
        {tested && (
          <p className="font-mono text-[10px] text-accent-green">
            Installed for testing ({project.test_files.length} files). The game loads it on next
            launch.
          </p>
        )}
        {testResult?.warnings.map((w, i) => (
          <p key={i} className="text-[10px] text-mjolnir-gold">
            {w}
          </p>
        ))}
      </div>

      <div className="flex flex-col gap-2 border-b border-border-subtle p-3">
        <h2 className="text-[10px] uppercase tracking-wider text-text-dim">Share it</h2>
        <button
          type="button"
          className={buttonPlain}
          disabled={projectBusy !== null || !hasChanges}
          title="Bake the mod into a .mjolnir archive anyone can install from the launcher."
          onClick={() => void exportMod()}
        >
          {projectBusy === "export" ? "Exporting…" : "Export .mjolnir archive"}
        </button>
        {exportResult && (
          <div className="flex flex-col gap-1">
            <p
              className="break-all font-mono text-[10px] text-accent-green"
              title={exportResult.archive}
            >
              Wrote {exportResult.archive} ({formatSize(exportResult.size)},{" "}
              {exportResult.chunk_count} chunk{exportResult.chunk_count === 1 ? "" : "s"}
              {exportResult.signed ? ", signed" : ""})
            </p>
            {exportResult.warnings.map((w, i) => (
              <p key={i} className="text-[10px] text-mjolnir-gold">
                {w}
              </p>
            ))}
          </div>
        )}
      </div>

      <PublishSection />
    </>
  );
}
