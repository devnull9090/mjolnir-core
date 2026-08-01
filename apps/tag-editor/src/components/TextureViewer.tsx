import { useState } from "react";
import { save } from "@tauri-apps/plugin-dialog";
import { useEditor } from "../stores/editor-store";

/** Zoom steps for the texture view; "fit" scales to the pane. */
const ZOOMS = [0.25, 0.5, 1, 2, 4] as const;

/** Viewer for a decoded Unreal texture: image on a checkerboard, plus export. */
export function TextureViewer() {
  const { texture, textureLoading, textureError, selectedTexture } = useEditor();
  const exportTexture = useEditor((s) => s.exportTexture);
  const [zoom, setZoom] = useState<number | "fit">("fit");
  const [wrote, setWrote] = useState<string | null>(null);

  if (textureLoading) {
    return <Centered>Decoding texture…</Centered>;
  }
  if (textureError) {
    return (
      <div className="flex min-h-0 flex-1 items-center justify-center px-8">
        <div className="max-w-lg border border-accent-red/40 bg-accent-red/5 px-4 py-3">
          <p className="text-sm text-text-primary">This texture could not be decoded.</p>
          <p className="mt-1 font-mono text-[11px] text-text-secondary">{textureError}</p>
        </div>
      </div>
    );
  }
  if (!texture) {
    return (
      <Centered>
        {selectedTexture === null ? "Select a texture to view." : "Nothing to show."}
      </Centered>
    );
  }

  const shownNote =
    texture.mip > 0 ? ` · shown at mip ${texture.mip} (${texture.width >> texture.mip}×${texture.height >> texture.mip})` : "";

  async function onExport() {
    if (!texture) return;
    const name = `${texture.path.split("/").pop() ?? "texture"}.png`;
    const dest = await save({ defaultPath: name });
    if (!dest) return;
    setWrote(null);
    const written = await exportTexture(dest);
    if (written !== null) {
      setWrote(`Wrote ${written.toLocaleString()} bytes to ${dest}`);
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <header className="border-b border-border-subtle bg-surface-primary px-6 py-4">
        <div className="flex flex-wrap items-baseline gap-3">
          <h1 className="min-w-0 truncate font-mono text-lg text-mjolnir-gold">
            {texture.path.split("/").pop()}
          </h1>
          <span className="font-mono text-xs text-text-dim">
            {texture.width}×{texture.height} · {texture.format.replace(/^PF_/, "")} ·{" "}
            {texture.num_mips} mips{shownNote}
          </span>
          <span className="ml-auto flex items-center gap-1">
            <button
              type="button"
              onClick={() => setZoom("fit")}
              className={`border px-2 py-0.5 text-[11px] ${
                zoom === "fit"
                  ? "border-mjolnir-gold/60 text-mjolnir-gold"
                  : "border-border-subtle text-text-secondary hover:bg-surface-hover"
              }`}
            >
              fit
            </button>
            {ZOOMS.map((z) => (
              <button
                key={z}
                type="button"
                onClick={() => setZoom(z)}
                className={`border px-2 py-0.5 text-[11px] ${
                  zoom === z
                    ? "border-mjolnir-gold/60 text-mjolnir-gold"
                    : "border-border-subtle text-text-secondary hover:bg-surface-hover"
                }`}
              >
                {z}×
              </button>
            ))}
            <button
              type="button"
              onClick={() => void onExport()}
              className="ml-2 border border-mjolnir-gold/60 px-2 py-0.5 text-[11px] text-mjolnir-gold hover:bg-mjolnir-gold/10"
              title="Decode at full size and save as PNG"
            >
              Export PNG…
            </button>
          </span>
        </div>
        <p className="mt-1 truncate font-mono text-[11px] text-text-secondary">{texture.path}</p>
        {wrote && <p className="mt-1 font-mono text-[10px] text-accent-green">{wrote}</p>}
      </header>

      <div
        className="min-h-0 flex-1 overflow-auto p-4"
        style={{
          backgroundImage:
            "linear-gradient(45deg, #151b28 25%, transparent 25%, transparent 75%, #151b28 75%), " +
            "linear-gradient(45deg, #151b28 25%, transparent 25%, transparent 75%, #151b28 75%)",
          backgroundSize: "24px 24px",
          backgroundPosition: "0 0, 12px 12px",
        }}
      >
        <img
          src={texture.png}
          alt={texture.path}
          className={zoom === "fit" ? "max-h-full max-w-full object-contain" : "max-w-none"}
          style={
            zoom === "fit"
              ? { imageRendering: "auto" }
              : {
                  width: (texture.width >> texture.mip) * zoom,
                  height: (texture.height >> texture.mip) * zoom,
                  imageRendering: zoom >= 2 ? "pixelated" : "auto",
                }
          }
        />
      </div>
    </div>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-0 flex-1 items-center justify-center text-sm text-text-dim">
      {children}
    </div>
  );
}
