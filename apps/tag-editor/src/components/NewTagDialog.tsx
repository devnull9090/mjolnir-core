import { useEffect, useRef, useState } from "react";
import { useEditor } from "../stores/editor-store";

/**
 * "New Tag": clone a shipped tag under a new path in the same group.
 *
 * The clone is part of the mod, not the installation: it reads as the donor
 * until its fields are edited, and becomes a package of its own when the mod
 * is tested or exported. A tag nothing references is never loaded, so the
 * dialog says where to point next.
 */
export function NewTagDialog() {
  const from = useEditor((s) => s.newTagFrom);
  const close = useEditor((s) => s.closeNewTag);
  const create = useEditor((s) => s.createNewTag);
  const [path, setPath] = useState("");
  const [assetReference, setAssetReference] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);

  // Seed the path from the donor each time the dialog opens: a clone usually
  // sits beside its donor with a new leaf.
  useEffect(() => {
    if (!from) return;
    setPath(`${from.short}_new`);
    setAssetReference("");
    setError(null);
    setBusy(false);
    const t = window.setTimeout(() => {
      inputRef.current?.focus();
      const at = from.short.length;
      inputRef.current?.setSelectionRange(at, at + 4);
    }, 0);
    return () => window.clearTimeout(t);
  }, [from]);

  if (!from) return null;

  const submit = async () => {
    if (busy) return;
    setBusy(true);
    const problem = await create(path, assetReference);
    setBusy(false);
    if (problem) setError(problem);
  };

  const leaf = path.split("/").pop() ?? path;

  return (
    <div
      className="fixed inset-0 z-40 bg-black/50"
      onPointerDown={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <form
        className="mx-auto mt-[15vh] flex w-[36rem] max-w-[90vw] flex-col gap-3 border border-border-subtle bg-surface-card p-4 shadow-2xl"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            e.preventDefault();
            close();
          }
        }}
      >
        <div className="flex items-baseline gap-2">
          <h2 className="text-xs uppercase tracking-wider text-text-dim">New tag</h2>
          <span className="min-w-0 truncate font-mono text-xs text-text-secondary" title={from.short}>
            from {from.short.split("/").pop()}.{from.group}
          </span>
        </div>

        <label className="flex flex-col gap-1">
          <span className="text-[11px] text-text-secondary">
            Path, without the group — the group stays <span className="font-mono">{from.group}</span>
          </span>
          <input
            ref={inputRef}
            className="w-full border border-border-subtle bg-surface-secondary px-3 py-2 font-mono text-sm text-text-primary outline-none placeholder:text-text-dim focus:border-mjolnir-gold"
            value={path}
            onChange={(e) => setPath(e.target.value)}
            placeholder="objects/weapons/pistol/pistol_mk2"
            spellCheck={false}
          />
          <span className="font-mono text-[10px] text-text-dim">
            {leaf ? `${leaf}.${from.group}` : " "}
          </span>
        </label>

        <label className="flex flex-col gap-1">
          <span className="text-[11px] text-text-secondary">
            Unreal asset to bind to <span className="text-text-dim">(optional)</span>
          </span>
          <input
            className="w-full border border-border-subtle bg-surface-secondary px-3 py-2 font-mono text-sm text-text-primary outline-none placeholder:text-text-dim focus:border-mjolnir-gold"
            value={assetReference}
            onChange={(e) => setAssetReference(e.target.value)}
            placeholder="Keep the donor's — or /Game/Blueprints/…/BP_Thing"
            spellCheck={false}
          />
          <span className="text-[10px] text-text-dim">
            Only groups with an Unreal side (objects, effects, sounds) have one. Leave it empty
            to share the donor's Blueprint or asset.
          </span>
        </label>

        <p className="text-[11px] text-text-dim">
          The clone starts as the donor is in this mod, and its own edits are recorded under the
          new name. Nothing references it yet: point a tag at{" "}
          <span className="font-mono text-text-secondary">
            {from.group}:{path.replace(/\//g, "\\")}
          </span>{" "}
          for the game to load it.
        </p>

        {error && (
          <p className="border border-accent-red/40 bg-accent-red/5 px-3 py-2 font-mono text-[11px] text-accent-red">
            {error}
          </p>
        )}

        <div className="flex justify-end gap-2">
          <button
            type="button"
            className="border border-border-subtle px-3 py-1 text-xs text-text-secondary hover:bg-surface-hover"
            onClick={close}
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={busy || !path.trim()}
            className="border border-mjolnir-gold/60 px-3 py-1 text-xs text-mjolnir-gold hover:bg-mjolnir-gold/10 disabled:opacity-40"
          >
            {busy ? "Creating…" : "Create"}
          </button>
        </div>
      </form>
    </div>
  );
}
