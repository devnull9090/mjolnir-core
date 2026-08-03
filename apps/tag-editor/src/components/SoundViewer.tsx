import { useState } from "react";
import { save } from "@tauri-apps/plugin-dialog";
import { useEditor } from "../stores/editor-store";

/** Seconds as `m:ss.s`, which reads better than a raw float for short cues. */
function duration(secs: number): string {
  const m = Math.floor(secs / 60);
  const s = secs - m * 60;
  return m > 0 ? `${m}:${s.toFixed(1).padStart(4, "0")}` : `${s.toFixed(2)}s`;
}

function bytes(n: number): string {
  if (n >= 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  if (n >= 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${n} B`;
}

/**
 * Viewer for one Wwise audio file.
 *
 * Playback is not wired up yet: the game encodes with Wwise Vorbis, which needs
 * its Ogg headers rebuilt before anything can decode it. Until that lands this
 * shows what the header says and exports the raw `.wem`.
 */
export function SoundViewer() {
  const { sound, soundLoading, soundError, selectedSound } = useEditor();
  const exportSound = useEditor((s) => s.exportSound);
  const [wrote, setWrote] = useState<string | null>(null);

  if (soundLoading) {
    return <Centered>Reading sound header…</Centered>;
  }
  if (soundError) {
    return (
      <div className="flex min-h-0 flex-1 items-center justify-center px-8">
        <div className="max-w-lg border border-accent-red/40 bg-accent-red/5 px-4 py-3">
          <p className="text-sm text-text-primary">This sound could not be read.</p>
          <p className="mt-1 font-mono text-[11px] text-text-secondary">{soundError}</p>
        </div>
      </div>
    );
  }
  if (!sound) {
    return (
      <Centered>
        {selectedSound === null ? "Select a sound to view." : "Nothing to show."}
      </Centered>
    );
  }

  const info = sound.info;
  const name = sound.path.split("/").pop() ?? "sound";

  async function onExport() {
    if (!sound) return;
    const dest = await save({ defaultPath: name });
    if (!dest) return;
    setWrote(null);
    const written = await exportSound(dest);
    if (written !== null) {
      setWrote(`Wrote ${written.toLocaleString()} bytes to ${dest}`);
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <header className="border-b border-border-subtle bg-surface-primary px-6 py-4">
        <div className="flex flex-wrap items-baseline gap-3">
          <h1 className="min-w-0 truncate font-mono text-lg text-mjolnir-gold">{name}</h1>
          {info && (
            <span className="font-mono text-xs text-text-dim">
              {info.codec} · {info.channels === 1 ? "mono" : `${info.channels} ch`} ·{" "}
              {(info.sample_rate / 1000).toFixed(1)} kHz
              {info.duration_secs !== null && ` · ${duration(info.duration_secs)}`}
            </span>
          )}
          <button
            type="button"
            onClick={() => void onExport()}
            className="ml-auto border border-mjolnir-gold/60 px-2 py-0.5 text-[11px] text-mjolnir-gold hover:bg-mjolnir-gold/10"
            title="Save the raw Wwise payload, ready for a converter"
          >
            Export .wem…
          </button>
        </div>
        <p className="mt-1 truncate font-mono text-[11px] text-text-secondary">{sound.path}</p>
        {wrote && <p className="mt-1 font-mono text-[10px] text-accent-green">{wrote}</p>}
      </header>

      <div className="min-h-0 flex-1 overflow-auto px-6 py-5">
        {/* Playback is deliberately absent rather than faked: nothing in the
            app can turn Wwise Vorbis into samples yet. */}
        <div className="mb-6 flex items-center gap-4 border border-border-subtle bg-surface-primary px-4 py-4">
          <div
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-border-subtle text-text-dim"
            title="Playback needs a Wwise Vorbis decoder, which is not built yet"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
              <path d="M4 2.5v11l9-5.5-9-5.5z" fill="currentColor" />
            </svg>
          </div>
          <div className="min-w-0 max-w-2xl">
            <p className="text-sm text-text-primary">Preview not available yet</p>
            <p className="mt-0.5 text-[11px] text-text-secondary">
              {info
                ? `${info.codec} has to be rebuilt into an Ogg stream before it can play. Export the .wem to convert it elsewhere in the meantime.`
                : (sound.error ?? "This file carries no readable audio header.")}
            </p>
          </div>
        </div>

        <dl className="grid grid-cols-[max-content_1fr] gap-x-6 gap-y-1.5 font-mono text-[11px]">
          <Row label="stored size" value={bytes(sound.size)} />
          {sound.language && <Row label="language" value={sound.language} />}
          {info && (
            <>
              <Row label="codec" value={`${info.codec} (tag 0x${info.format_tag.toString(16).padStart(4, "0")})`} />
              <Row label="channels" value={String(info.channels)} />
              <Row label="sample rate" value={`${info.sample_rate.toLocaleString()} Hz`} />
              {info.sample_count !== null && (
                <Row label="samples" value={info.sample_count.toLocaleString()} />
              )}
              {info.duration_secs !== null && (
                <Row label="duration" value={duration(info.duration_secs)} />
              )}
              <Row
                label="bit rate"
                value={`${Math.round((info.avg_bytes_per_sec * 8) / 1000).toLocaleString()} kbps`}
              />
              <Row label="audio data" value={bytes(info.data_size)} />
              <Row label="riff chunks" value={info.chunks.join(", ")} />
            </>
          )}
        </dl>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt className="text-text-dim">{label}</dt>
      <dd className="truncate text-text-primary">{value}</dd>
    </>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-0 flex-1 items-center justify-center text-sm text-text-dim">
      {children}
    </div>
  );
}
