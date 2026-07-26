import { useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { useEditor } from "../stores/editor-store";

/** Shown until an installation is open. */
export function SetupPanel() {
  const { status, error, note, paks, oodle } = useEditor();
  const openInstall = useEditor((s) => s.open);
  const [paksPath, setPaksPath] = useState(paks ?? "");
  const [oodlePath, setOodlePath] = useState(oodle ?? "");

  async function pick(kind: "paks" | "oodle") {
    const selected = await open({
      directory: kind === "paks",
      multiple: false,
      filters: kind === "oodle" ? [{ name: "Oodle", extensions: ["dll"] }] : undefined,
    });
    if (typeof selected === "string") {
      if (kind === "paks") setPaksPath(selected);
      else setOodlePath(selected);
    }
  }

  const busy = status === "detecting" || status === "opening";

  return (
    <div className="flex h-full items-center justify-center p-8">
      <div className="w-full max-w-xl">
        <h1 className="text-xl font-bold text-mjolnir-gold">MJOLNIR Tag Editor</h1>
        <p className="mt-2 text-sm text-text-secondary">
          Reads Blam tag definitions from your own installation of Halo Campaign Evolved. Nothing
          is modified and no tag content is written to disk.
        </p>

        {note && (
          <p className="mt-4 border-l-2 border-mjolnir-gold bg-surface-card px-4 py-3 text-xs text-text-secondary">
            {note}
          </p>
        )}
        {error && (
          <p className="mt-4 border-l-2 border-accent-red bg-surface-card px-4 py-3 text-xs text-accent-red">
            {error}
          </p>
        )}

        <div className="mt-6 space-y-4">
          <Field
            label="Paks folder"
            hint="Meteorite\Content\Paks inside the game install"
            value={paksPath}
            onChange={setPaksPath}
            onBrowse={() => void pick("paks")}
          />
          <Field
            label="Oodle DLL"
            hint="oo2core_*_win64.dll from any Unreal Engine install"
            value={oodlePath}
            onChange={setOodlePath}
            onBrowse={() => void pick("oodle")}
          />
        </div>

        <button
          type="button"
          disabled={busy || !paksPath || !oodlePath}
          onClick={() => void openInstall(paksPath, oodlePath)}
          className="mt-6 w-full bg-mjolnir-gold px-4 py-2.5 text-sm font-semibold text-surface-primary transition-colors hover:bg-mjolnir-gold-dim disabled:cursor-not-allowed disabled:opacity-40"
        >
          {busy ? "Opening…" : "Open installation"}
        </button>
      </div>
    </div>
  );
}

function Field({
  label,
  hint,
  value,
  onChange,
  onBrowse,
}: {
  label: string;
  hint: string;
  value: string;
  onChange: (v: string) => void;
  onBrowse: () => void;
}) {
  return (
    <div>
      <label className="block text-xs font-semibold uppercase text-text-secondary">
        {label}
      </label>
      <div className="mt-1.5 flex gap-2">
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="min-w-0 flex-1 border border-border-subtle bg-surface-card px-3 py-2 font-mono text-xs outline-none focus:border-mjolnir-gold"
        />
        <button
          type="button"
          onClick={onBrowse}
          className="shrink-0 border border-border-subtle px-3 py-2 text-xs text-text-secondary transition-colors hover:bg-surface-hover"
        >
          Browse
        </button>
      </div>
      <p className="mt-1 font-mono text-[10px] text-text-dim">{hint}</p>
    </div>
  );
}
