/**
 * The gallery submission flow, in one place.
 *
 * Every surface that adds screenshots — a mod's public page, its owner's
 * manage page, and a tool page for moderators — mounts this, so
 * drag-and-drop, previews, per-file descriptions and the upload queue exist
 * once. `owner` decides where the files go; `variant` decides how much room
 * it takes: a full dashed panel where uploading is the point of the page, a
 * one-line strip where the gallery is just another section.
 *
 * Files go up one at a time rather than all at once. A gallery submission can
 * be a 64 MiB video, and a handful of those in parallel would starve each
 * other of bandwidth for no gain — and the reader could not tell which of the
 * five half-finished bars was the one that failed.
 */
import { useCallback, useState } from "react";

import { HubError } from "../client";
import type { Media, MediaOwner } from "../types";
import { useHub } from "./context";
import {
  FileDropzone,
  type FileRules,
  RejectionNote,
  StagedFileRow,
  type StagedFile,
  useFileStaging,
  usePastedFiles,
} from "./FileDrop";
import { formatBytes } from "./format";
import { ImagePlusIcon } from "./icons";
import { ActionButton } from "./primitives";

/** Mirrors what `POST /mods/{slug}/media` enforces (lib/api/community.ts). */
export const MEDIA_RULES: FileRules = {
  accept: "image/png,image/jpeg,image/webp,video/mp4,video/webm",
  maxBytes: { "image/": 8 * 1024 * 1024, "video/": 64 * 1024 * 1024 },
  maxFiles: 10,
};

export const MEDIA_HINT = "png · jpeg · webp up to 8 MiB · mp4 · webm up to 64 MiB";

function message(e: unknown): string {
  if (e instanceof HubError && e.needsAuth) return "Sign in again — that upload was not accepted.";
  return e instanceof Error ? e.message : String(e);
}

export function MediaUploader({
  owner,
  variant = "panel",
  onUploaded,
  className = "",
}: {
  /** The mod or tool the files are being added to. */
  owner: MediaOwner;
  variant?: "panel" | "inline";
  /** Fired per accepted item, so the gallery can show it without a refetch. */
  onUploaded?: (media: Media) => void;
  className?: string;
}) {
  const { client } = useHub();
  const staging = useFileStaging(MEDIA_RULES);
  const [busy, setBusy] = useState(false);
  // Empty descriptions only turn red once the reader has tried to upload —
  // marking them on sight would scold them for files they just dropped.
  const [flagMissing, setFlagMissing] = useState(false);

  const { files, add, update, remove, clear, rejections, dismissRejections } = staging;
  usePastedFiles(MEDIA_RULES, add, !busy);
  const missing = files.filter((f) => !f.caption.trim()).length;
  const totalBytes = files.reduce((n, f) => n + f.file.size, 0);

  const uploadOne = useCallback(
    async (item: StagedFile) => {
      const caption = item.caption.trim();
      if (!caption) return;
      update(item.key, { status: "uploading", progress: 0, error: null });
      // Progress fires per chunk; only a changed whole percent is worth a
      // re-render of the list.
      let lastPct = -1;
      try {
        const created = await client.uploadMedia(owner, item.file, caption, (p) => {
          const pct = Math.round(p * 100);
          if (pct === lastPct) return;
          lastPct = pct;
          update(item.key, { progress: p });
        });
        // Straight out of the staging list and into the gallery above: the
        // file moving is the confirmation, so nothing needs dismissing.
        remove(item.key);
        onUploaded?.(created);
        return created;
      } catch (e) {
        update(item.key, { status: "error", error: message(e), progress: 0 });
        return undefined;
      }
    },
    [client, onUploaded, owner, remove, update],
  );

  const uploadAll = async () => {
    if (busy) return;
    if (missing > 0) {
      setFlagMissing(true);
      return;
    }
    setBusy(true);
    // Every failure belongs to a file and is reported on that file's row, so
    // there is nothing left for a banner over the whole list to say.
    for (const item of files) {
      if (item.status === "uploading") continue;
      await uploadOne(item);
    }
    setFlagMissing(false);
    setBusy(false);
  };

  const label =
    variant === "panel" ? (
      <>
        Drag screenshots or videos here, paste, or{" "}
        <span className="text-[var(--mj-gold)]">browse</span>
      </>
    ) : (
      <>
        Drop screenshots or videos here, paste, or{" "}
        <span className="text-[var(--mj-gold)]">browse</span>
      </>
    );

  return (
    <div className={`space-y-3 ${className}`}>
      <FileDropzone
        rules={MEDIA_RULES}
        variant={variant}
        onFiles={add}
        disabled={busy}
        label={label}
        ariaLabel="Add screenshots or videos"
        hint={MEDIA_HINT}
        icon={
          <ImagePlusIcon
            className={
              variant === "panel"
                ? "w-7 h-7 text-[var(--mj-text-dim)]"
                : "w-4 h-4 shrink-0 text-[var(--mj-text-dim)]"
            }
          />
        }
      />

      <RejectionNote problems={rejections} onDismiss={dismissRejections} />

      {files.length > 0 && (
        <>
          <ul className="space-y-2">
            {files.map((item) => (
              <StagedFileRow
                key={item.key}
                item={item}
                captionMissing={flagMissing && !item.caption.trim()}
                onCaptionChange={(caption) => update(item.key, { caption })}
                onRemove={() => remove(item.key)}
                onRetry={item.status === "error" ? () => void uploadOne(item) : undefined}
              />
            ))}
          </ul>

          <div className="flex flex-wrap items-center gap-2">
            <ActionButton onClick={() => void uploadAll()} disabled={busy} size="sm">
              {busy
                ? "Uploading…"
                : `Upload ${files.length} file${files.length === 1 ? "" : "s"}`}
            </ActionButton>
            <ActionButton onClick={clear} disabled={busy} tone="neutral" size="sm">
              Clear
            </ActionButton>
            <span className="text-[11px] text-[var(--mj-text-dim)]">
              {formatBytes(totalBytes)} total
              {missing > 0 && ` · ${missing} still need${missing === 1 ? "s" : ""} a description`}
            </span>
          </div>
        </>
      )}
    </div>
  );
}
