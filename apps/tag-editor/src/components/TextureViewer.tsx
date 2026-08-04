import { useState } from "react";
import { open, save } from "@tauri-apps/plugin-dialog";
import { useEditor } from "../stores/editor-store";
import { isTauri } from "../lib/mock";

/** Zoom steps for the texture view; "fit" scales to the pane. */
const ZOOMS = [0.25, 0.5, 1, 2, 4] as const;

/** Viewer for a decoded Unreal texture: image on a checkerboard, plus export
 *  and — for formats that can be encoded — replacing its pixels. */
export function TextureViewer() {
  const { texture, textureLoading, textureError, selectedTexture } = useEditor();
  const exportTexture = useEditor((s) => s.exportTexture);
  const swapTexture = useEditor((s) => s.swapTexture);
  const revertTexture = useEditor((s) => s.revertTexture);
  const textureSwapping = useEditor((s) => s.textureSwapping);
  const swapReport = useEditor((s) => s.swapReport);
  const project = useEditor((s) => s.project);
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

  async function onReplace() {
    // Outside Tauri (browser dev against the mock) any path keeps the flow
    // walkable, the same shape as the mod panel's folder picker.
    const picked = isTauri
      ? await open({
          multiple: false,
          filters: [{ name: "PNG image", extensions: ["png"] }],
        })
      : "(mock).png";
    if (typeof picked !== "string") return;
    setWrote(null);
    await swapTexture(picked);
  }

  // A swap is a mod edit, so it needs somewhere to be saved. Everything else
  // in the viewer works without a project.
  const swapBlocked = texture.unsupported
    ? texture.unsupported
    : !project
      ? "Create or open a mod project first — a swap is saved as part of a mod."
      : null;

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
            <button
              type="button"
              onClick={() => void onReplace()}
              disabled={swapBlocked !== null || textureSwapping}
              title={swapBlocked ?? "Replace these pixels with a PNG"}
              className="border border-mjolnir-gold/60 px-2 py-0.5 text-[11px] text-mjolnir-gold hover:bg-mjolnir-gold/10 disabled:cursor-not-allowed disabled:border-border-subtle disabled:text-text-dim disabled:hover:bg-transparent"
            >
              {textureSwapping ? "Encoding…" : "Replace…"}
            </button>
            {texture.replaced && (
              <button
                type="button"
                onClick={() => void revertTexture()}
                disabled={textureSwapping}
                title="Drop this swap and go back to what the game ships"
                className="border border-border-subtle px-2 py-0.5 text-[11px] text-text-secondary hover:bg-surface-hover disabled:cursor-not-allowed disabled:text-text-dim"
              >
                Revert
              </button>
            )}
          </span>
        </div>
        <p className="mt-1 truncate font-mono text-[11px] text-text-secondary">{texture.path}</p>
        {wrote && <p className="mt-1 font-mono text-[10px] text-accent-green">{wrote}</p>}

        {texture.unsupported && (
          <p className="mt-2 border-l-2 border-mjolnir-gold-dim bg-surface-card/60 px-3 py-1.5 text-[11px] text-text-secondary">
            {texture.unsupported}
          </p>
        )}

        {textureSwapping && (
          <p className="mt-2 font-mono text-[11px] text-text-secondary">
            Re-encoding every mip at the shipped size and format — this takes a
            few seconds on a large texture.
          </p>
        )}

        {texture.replaced && !textureSwapping && (
          <div className="mt-2 border-l-2 border-accent-green bg-accent-green/5 px-3 py-1.5">
            <p className="text-[11px] text-text-primary">
              This mod replaces this texture.{" "}
              {swapReport ? (
                <span className="text-text-secondary">
                  Re-encoded {swapReport.mips} mip
                  {swapReport.mips === 1 ? "" : "s"};{" "}
                  {swapReport.changed.toLocaleString()} of{" "}
                  {swapReport.payload.toLocaleString()} payload bytes changed;
                  readback error {swapReport.error.toFixed(2)} / 255.
                </span>
              ) : (
                <span className="text-text-secondary">
                  Showing the replacement image the recipe holds. It is
                  re-encoded against the game when the mod is tested or
                  exported.
                </span>
              )}
            </p>
          </div>
        )}
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
        {/* Straight after a swap, show the readback — the payload decoded
            again, which is what the game will really draw, block-compression
            losses and all. On a later visit only the source image is on hand. */}
        <img
          src={swapReport?.png ?? texture.png}
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
