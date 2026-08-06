/**
 * File staging: the drop target, the list of chosen files, and one row of it.
 *
 * Three pieces kept deliberately separate, because the surfaces that upload
 * want different amounts of this. The mod gallery takes all three — drop a
 * dozen screenshots, caption each, watch them go. The release archive takes
 * only `<FileDropzone>`, since one file goes straight up with no staging.
 *
 * Validation lives here rather than in each caller because the browser applies
 * `accept` to the file picker and nothing else: a dragged file arrives
 * unfiltered, and a dropped 200 MiB video would otherwise travel the whole way
 * to the server to be told no. The rules mirror what the API enforces, so the
 * answer is the same either way — just faster and in a place that can explain
 * itself.
 */
import type { ReactNode } from "react";
import { useCallback, useEffect, useId, useRef, useState, useSyncExternalStore } from "react";

import { formatBytes } from "./format";
import { AlertIcon, CheckIcon, CloseIcon, FileIcon, PlayIcon, TrashIcon } from "./icons";
import { Spinner } from "./primitives";

/** What a surface will take, in the shape the picker and a drop both need. */
export interface FileRules {
  /** The `accept` attribute, also applied by hand to dropped files. */
  accept: string;
  /**
   * Byte ceiling per MIME prefix — `{ "image/": 8 MiB, "video/": 64 MiB }`.
   * The `*` key is the fallback for anything unmatched.
   */
  maxBytes?: Record<string, number>;
  /** Refuse more than this many files at once. */
  maxFiles?: number;
}

export type FileKind = "image" | "video" | "file";

export interface StagedFile {
  /** Stable across re-renders and independent of list position. */
  key: string;
  file: File;
  kind: FileKind;
  /** Object URL for image/video previews; null for anything else. */
  preview: string | null;
  /** Alt text or description, for surfaces that require one. */
  caption: string;
  status: "ready" | "uploading" | "done" | "error";
  /** 0–1 while uploading; transports that cannot report it stay at 0. */
  progress: number;
  error: string | null;
}

// ── Validation ────────────────────────────────────────────────────────

/** The browser's own `accept` matching: `.ext`, `type/*`, or an exact type. */
export function matchesAccept(file: File, accept: string): boolean {
  const tokens = accept
    .split(",")
    .map((t) => t.trim().toLowerCase())
    .filter(Boolean);
  if (tokens.length === 0) return true;
  const type = file.type.toLowerCase();
  const name = file.name.toLowerCase();
  return tokens.some((t) => {
    if (t.startsWith(".")) return name.endsWith(t);
    if (t.endsWith("/*")) return type.startsWith(t.slice(0, -1));
    return type === t;
  });
}

/** The ceiling this file is held to, or undefined when it is unbounded. */
export function limitFor(file: File, rules: FileRules): number | undefined {
  const limits = rules.maxBytes;
  if (!limits) return undefined;
  // Longest matching prefix wins, so "image/png" can differ from "image/".
  let best: { prefix: string; bytes: number } | null = null;
  for (const [prefix, bytes] of Object.entries(limits)) {
    if (prefix === "*") continue;
    if (file.type.toLowerCase().startsWith(prefix) && (!best || prefix.length > best.prefix.length)) {
      best = { prefix, bytes };
    }
  }
  return best?.bytes ?? limits["*"];
}

export function kindOf(file: File): FileKind {
  if (file.type.startsWith("image/")) return "image";
  if (file.type.startsWith("video/")) return "video";
  return "file";
}

/** Null when the file is acceptable, else a sentence naming what is wrong. */
export function checkFile(file: File, rules: FileRules): string | null {
  if (!matchesAccept(file, rules.accept)) {
    return `${file.name} — not a file type this accepts.`;
  }
  const limit = limitFor(file, rules);
  if (limit !== undefined && file.size > limit) {
    return `${file.name} — ${formatBytes(file.size)}, over the ${formatBytes(limit)} limit.`;
  }
  if (file.size === 0) return `${file.name} — the file is empty.`;
  return null;
}

// ── Page-wide drag tracking ───────────────────────────────────────────

/**
 * A file dropped anywhere but a drop target makes the browser navigate to it,
 * which throws away whatever the page was holding. One document-level guard,
 * mounted while any dropzone is on screen, swallows those drops — and the
 * same listeners tell every zone that a drag is in flight, so they can light
 * up before the pointer reaches them.
 */
const dragListeners = new Set<() => void>();
let dragDepth = 0;
let guardInstalled = false;

function dragCarriesFiles(e: DragEvent): boolean {
  return Array.from(e.dataTransfer?.types ?? []).includes("Files");
}

function emitDrag() {
  for (const listener of dragListeners) listener();
}

function installGuard() {
  if (guardInstalled || typeof document === "undefined") return;
  guardInstalled = true;
  document.addEventListener("dragenter", (e) => {
    if (!dragCarriesFiles(e)) return;
    dragDepth++;
    if (dragDepth === 1) emitDrag();
  });
  document.addEventListener("dragleave", (e) => {
    if (!dragCarriesFiles(e)) return;
    dragDepth = Math.max(0, dragDepth - 1);
    if (dragDepth === 0) emitDrag();
  });
  // Both of these must be prevented or the browser opens the file itself.
  document.addEventListener("dragover", (e) => {
    if (dragCarriesFiles(e)) e.preventDefault();
  });
  document.addEventListener("drop", (e) => {
    if (!dragCarriesFiles(e)) return;
    e.preventDefault();
    dragDepth = 0;
    emitDrag();
  });
}

function subscribeDrag(listener: () => void) {
  installGuard();
  dragListeners.add(listener);
  return () => {
    dragListeners.delete(listener);
  };
}

/** True while a file drag is anywhere over the page. */
export function useDocumentDrag(): boolean {
  return useSyncExternalStore(
    subscribeDrag,
    () => dragDepth > 0,
    () => false,
  );
}

// ── The drop target ───────────────────────────────────────────────────

export function FileDropzone({
  rules,
  onFiles,
  multiple = true,
  disabled = false,
  busy = false,
  variant = "panel",
  label,
  hint,
  icon,
  ariaLabel,
  className = "",
}: {
  rules: FileRules;
  /**
   * One call per selection, carrying both halves of it: the files that passed
   * `rules`, and a sentence for each that did not. Both in one call so the
   * receiver can replace the previous batch's complaints atomically — two
   * callbacks would race, and the second would wipe the first.
   */
  onFiles: (accepted: File[], problems: string[]) => void;
  multiple?: boolean;
  disabled?: boolean;
  /** Draws a spinner in place of the icon; the zone stops taking files. */
  busy?: boolean;
  /** `panel` is the full dashed box; `inline` is a one-line strip. */
  variant?: "panel" | "inline";
  label: ReactNode;
  hint?: ReactNode;
  icon?: ReactNode;
  /** Needed when `label` is not plain text. */
  ariaLabel?: string;
  className?: string;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const dragging = useDocumentDrag();
  const hintId = useId();
  const inert = disabled || busy;

  const take = useCallback(
    (list: FileList | File[] | null) => {
      const incoming = [...(list ?? [])];
      if (incoming.length === 0) return;
      const chosen = multiple ? incoming : incoming.slice(0, 1);
      const accepted: File[] = [];
      const problems: string[] = [];
      for (const file of chosen) {
        const problem = checkFile(file, rules);
        if (problem) problems.push(problem);
        else accepted.push(file);
      }
      onFiles(accepted, problems);
    },
    [multiple, onFiles, rules],
  );

  const shell =
    variant === "panel"
      ? "flex-col gap-2 px-4 py-8 sm:py-10 rounded-xl border-2"
      : "flex-row gap-2 px-3 py-2.5 rounded-lg border";

  const border = over
    ? "border-[var(--mj-gold)] bg-[var(--mj-gold)]/10"
    : dragging && !inert
      ? "border-[var(--mj-gold)]/50 bg-[var(--mj-gold)]/5"
      : "border-[var(--mj-border-bright)] hover:border-[var(--mj-gold)]/50 hover:bg-[var(--mj-surface-hover)]/30";

  return (
    <div className={className}>
      <button
        type="button"
        disabled={inert}
        aria-label={ariaLabel}
        aria-describedby={hint ? hintId : undefined}
        onClick={() => inputRef.current?.click()}
        onDragEnter={(e) => {
          if (inert || !dragCarriesFiles(e.nativeEvent)) return;
          e.preventDefault();
          setOver(true);
        }}
        onDragOver={(e) => {
          if (inert || !dragCarriesFiles(e.nativeEvent)) return;
          // Without this the drop never fires; `copy` sets the cursor.
          e.preventDefault();
          e.dataTransfer.dropEffect = "copy";
        }}
        onDragLeave={(e) => {
          // Fires for every child too, so only a leave of the zone counts.
          if (e.currentTarget.contains(e.relatedTarget as Node | null)) return;
          setOver(false);
        }}
        onDrop={(e) => {
          if (inert) return;
          e.preventDefault();
          setOver(false);
          take(e.dataTransfer.files);
        }}
        className={`flex w-full items-center justify-center border-dashed text-center transition-colors cursor-pointer disabled:cursor-default disabled:opacity-50 ${shell} ${border}`}
      >
        {busy ? <Spinner className="w-5 h-5 shrink-0" /> : icon}
        <span
          className={
            variant === "panel"
              ? "text-sm text-[var(--mj-text-muted)]"
              : "text-xs text-[var(--mj-text-muted)] min-w-0 truncate"
          }
        >
          {label}
        </span>
        {hint && variant === "panel" && (
          <span id={hintId} className="text-[11px] text-[var(--mj-text-dim)]">
            {hint}
          </span>
        )}
      </button>

      {hint && variant === "inline" && (
        <p id={hintId} className="mt-1 text-[11px] text-[var(--mj-text-dim)]">
          {hint}
        </p>
      )}

      <input
        ref={inputRef}
        type="file"
        accept={rules.accept}
        multiple={multiple}
        className="hidden"
        onChange={(e) => {
          take(e.target.files);
          // Reset, or choosing the same file twice fires no change event.
          e.target.value = "";
        }}
      />
    </div>
  );
}

/**
 * Ctrl+V as an upload path: the shortest route there is from a screenshot key
 * to a gallery. Bound to the window rather than the zone because nothing
 * focuses a drop target before pasting — and a paste only ever carries files
 * when the reader meant it to, so a stray Ctrl+V in a comment box is inert.
 *
 * `onFiles` matches `<FileDropzone>`'s, so both can hand off to the same
 * `useFileStaging().add`.
 */
export function usePastedFiles(
  rules: FileRules,
  onFiles: (accepted: File[], problems: string[]) => void,
  enabled = true,
) {
  useEffect(() => {
    if (!enabled || typeof window === "undefined") return;
    const onPaste = (e: ClipboardEvent) => {
      const pasted = [...(e.clipboardData?.files ?? [])];
      if (pasted.length === 0) return;
      const accepted: File[] = [];
      const problems: string[] = [];
      for (const file of pasted) {
        const problem = checkFile(file, rules);
        if (problem) problems.push(problem);
        else accepted.push(file);
      }
      onFiles(accepted, problems);
    };
    window.addEventListener("paste", onPaste);
    return () => window.removeEventListener("paste", onPaste);
  }, [enabled, onFiles, rules]);
}

// ── The staged list ───────────────────────────────────────────────────

export interface FileStaging {
  files: StagedFile[];
  /** Why files were turned away, as sentences; replaced by the next add. */
  rejections: string[];
  /**
   * Stage what passed and post what did not — the shape `<FileDropzone>`'s
   * `onFiles` hands over, so it can be passed straight through. `problems`
   * comes from the zone's own check; anything this refuses on top of that
   * (a duplicate, one file too many) is appended to it.
   */
  add: (files: File[], problems?: string[]) => void;
  update: (key: string, patch: Partial<Omit<StagedFile, "key" | "file">>) => void;
  remove: (key: string) => void;
  clear: () => void;
  dismissRejections: () => void;
}

let stagedSeq = 0;

/**
 * Owns the chosen-but-not-yet-uploaded files and their preview URLs.
 *
 * Every preview is an object URL, which pins the file in memory until it is
 * revoked — so this revokes on removal, on clear, and on unmount. A component
 * that mints them inline in JSX (the easy mistake) leaks one per render.
 */
export function useFileStaging(rules: FileRules): FileStaging {
  const [files, setFiles] = useState<StagedFile[]>([]);
  const [rejections, setRejections] = useState<string[]>([]);

  // The list is mirrored in a ref and every mutation is computed against it
  // rather than inside a `setFiles` updater. Updaters must be pure, and these
  // mint and revoke object URLs — under StrictMode's double invocation that
  // would leak one per added file, and the unmount cleanup below would close
  // over the empty first render besides.
  const live = useRef<StagedFile[]>([]);
  useEffect(
    () => () => {
      for (const f of live.current) if (f.preview) URL.revokeObjectURL(f.preview);
      live.current = [];
    },
    [],
  );

  const commit = useCallback((next: StagedFile[]) => {
    live.current = next;
    setFiles(next);
  }, []);

  const add = useCallback(
    (incoming: File[], rejected: string[] = []) => {
      const prev = live.current;
      const problems = [...rejected];
      const seen = new Set(prev.map((f) => `${f.file.name}:${f.file.size}:${f.file.lastModified}`));
      const room = rules.maxFiles === undefined ? Infinity : rules.maxFiles - prev.length;
      const next: StagedFile[] = [];

      for (const file of incoming) {
        const id = `${file.name}:${file.size}:${file.lastModified}`;
        if (seen.has(id)) {
          problems.push(`${file.name} — already staged.`);
          continue;
        }
        if (next.length >= room) {
          problems.push(`${file.name} — over the limit of ${rules.maxFiles} at a time.`);
          continue;
        }
        seen.add(id);
        const kind = kindOf(file);
        next.push({
          key: `staged-${++stagedSeq}`,
          file,
          kind,
          preview: kind === "file" ? null : URL.createObjectURL(file),
          caption: "",
          status: "ready",
          progress: 0,
          error: null,
        });
      }

      setRejections(problems);
      if (next.length > 0) commit([...prev, ...next]);
    },
    [commit, rules.maxFiles],
  );

  const update = useCallback<FileStaging["update"]>(
    (key, patch) => commit(live.current.map((f) => (f.key === key ? { ...f, ...patch } : f))),
    [commit],
  );

  const remove = useCallback(
    (key: string) => {
      const going = live.current.find((f) => f.key === key);
      if (going?.preview) URL.revokeObjectURL(going.preview);
      commit(live.current.filter((f) => f.key !== key));
    },
    [commit],
  );

  const clear = useCallback(() => {
    for (const f of live.current) if (f.preview) URL.revokeObjectURL(f.preview);
    commit([]);
    setRejections([]);
  }, [commit]);

  const dismissRejections = useCallback(() => setRejections([]), []);

  return { files, rejections, add, update, remove, clear, dismissRejections };
}

// ── One staged file ───────────────────────────────────────────────────

function Thumb({ item }: { item: StagedFile }) {
  // Deliberately small on a phone: every pixel it gives up goes to the
  // description field beside it, which is the part that has to be typed in.
  const box =
    "w-16 h-11 sm:w-24 sm:h-16 shrink-0 rounded-md border border-[var(--mj-border)] bg-[var(--mj-bg)] object-cover";
  if (item.kind === "image" && item.preview) {
    // Plain <img>: an object URL has nothing for next/image to optimise, and
    // this also renders inside the launcher's Vite build.
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={item.preview} alt="" className={box} />;
  }
  if (item.kind === "video" && item.preview) {
    return (
      <span className="relative shrink-0">
        {/* preload="metadata" paints the first frame without fetching the
            whole file — enough for a thumbnail of a 64 MiB clip. */}
        <video src={item.preview} preload="metadata" muted className={box} />
        <span className="absolute inset-0 flex items-center justify-center">
          <PlayIcon filled className="w-5 h-5 text-[var(--mj-text)] drop-shadow" />
        </span>
      </span>
    );
  }
  return (
    <span className={`${box} flex items-center justify-center`}>
      <FileIcon className="w-5 h-5 text-[var(--mj-text-dim)]" />
    </span>
  );
}

export function StagedFileRow({
  item,
  onCaptionChange,
  onRemove,
  onRetry,
  captionPlaceholder = "Describe it (required)",
  captionMaxLength = 500,
  captionMissing = false,
}: {
  item: StagedFile;
  /** Omit to hide the caption field entirely. */
  onCaptionChange?: (value: string) => void;
  onRemove: () => void;
  onRetry?: () => void;
  captionPlaceholder?: string;
  captionMaxLength?: number;
  /** Highlights the empty caption once the reader has tried to upload. */
  captionMissing?: boolean;
}) {
  const pct = Math.round(item.progress * 100);
  return (
    <li className="flex items-start gap-3 rounded-lg border border-[var(--mj-border)] bg-[var(--mj-surface)]/50 p-2.5">
      <Thumb item={item} />

      <div className="min-w-0 flex-1 space-y-1.5">
        <div className="flex items-baseline gap-2">
          <span className="min-w-0 truncate text-xs text-[var(--mj-text)]" title={item.file.name}>
            {item.file.name}
          </span>
          <span className="shrink-0 text-[11px] text-[var(--mj-text-dim)]">
            {formatBytes(item.file.size)}
          </span>
        </div>

        {onCaptionChange && item.status !== "done" && (
          <input
            value={item.caption}
            onChange={(e) => onCaptionChange(e.target.value)}
            disabled={item.status === "uploading"}
            maxLength={captionMaxLength}
            placeholder={captionPlaceholder}
            aria-label={`Description for ${item.file.name}`}
            aria-invalid={captionMissing || undefined}
            className={`w-full rounded-lg border bg-[var(--mj-bg)] px-2.5 py-2 text-xs text-[var(--mj-text)] placeholder:text-[var(--mj-text-dim)] focus:outline-none disabled:opacity-50 ${
              captionMissing
                ? "border-[var(--mj-red)]/60"
                : "border-[var(--mj-border)] focus:border-[var(--mj-gold)]/60"
            }`}
          />
        )}

        {item.status === "uploading" && (
          <div
            role="progressbar"
            aria-valuenow={pct}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={`Uploading ${item.file.name}`}
            className="h-1 overflow-hidden rounded-full bg-[var(--mj-surface-hover)]"
          >
            <div
              className="h-full rounded-full bg-[var(--mj-gold)] transition-[width] duration-150"
              // An indeterminate transport reports nothing; show a sliver
              // rather than an empty bar so it never looks stalled.
              style={{ width: `${Math.max(pct, 4)}%` }}
            />
          </div>
        )}

        {item.status === "done" && (
          <p className="flex items-center gap-1 text-[11px] text-[var(--mj-green)]">
            <CheckIcon className="w-3 h-3" />
            uploaded
          </p>
        )}

        {item.status === "error" && item.error && (
          <p className="flex items-start gap-1.5 text-[11px] text-[var(--mj-red)]">
            <AlertIcon className="mt-px w-3 h-3 shrink-0" />
            <span className="min-w-0">
              {item.error}
              {onRetry && (
                <button
                  type="button"
                  onClick={onRetry}
                  className="ml-1.5 underline cursor-pointer hover:text-[var(--mj-text)]"
                >
                  Retry
                </button>
              )}
            </span>
          </p>
        )}
      </div>

      <button
        type="button"
        onClick={onRemove}
        disabled={item.status === "uploading"}
        aria-label={`Remove ${item.file.name}`}
        title="Remove"
        className="-m-1 shrink-0 rounded p-2 text-[var(--mj-text-dim)] transition-colors hover:text-[var(--mj-red)] disabled:opacity-30 cursor-pointer disabled:cursor-default"
      >
        {item.status === "done" ? <CloseIcon className="w-4 h-4" /> : <TrashIcon className="w-4 h-4" />}
      </button>
    </li>
  );
}

/** The "that file cannot go" list, dismissible so it never blocks the view. */
export function RejectionNote({
  problems,
  onDismiss,
}: {
  problems: string[];
  onDismiss: () => void;
}) {
  if (problems.length === 0) return null;
  return (
    <div className="flex items-start gap-2 rounded-lg border border-[var(--mj-amber)]/40 bg-[var(--mj-amber)]/10 px-3 py-2 text-xs text-[var(--mj-amber)]">
      <AlertIcon className="mt-0.5 w-3.5 h-3.5 shrink-0" />
      <ul className="min-w-0 flex-1 space-y-0.5">
        {problems.map((p, i) => (
          <li key={i}>{p}</li>
        ))}
      </ul>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss"
        className="-m-1 shrink-0 rounded p-1 hover:text-[var(--mj-text)] cursor-pointer"
      >
        <CloseIcon className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}
