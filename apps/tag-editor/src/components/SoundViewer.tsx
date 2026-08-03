import { useState } from "react";
import { save } from "@tauri-apps/plugin-dialog";
import { useEditor } from "../stores/editor-store";
import { SoundPlayer } from "./SoundPlayer";

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
 * Viewer for one Wwise audio file: play it, read its header, export the raw
 * `.wem`, and see which Wwise events play it.
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
  const id = sound.path.split("/").pop() ?? "sound";
  // Wwise names media numerically; the event that plays it is the only
  // readable name there is, so it leads when one exists.
  const name = sound.events[0]?.name ?? id;

  async function onExport() {
    if (!sound) return;
    const dest = await save({ defaultPath: id });
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
        <div className="mb-6">
          {info ? (
            <SoundPlayer index={selectedSound ?? 0} />
          ) : (
            // A sound bank has no audio of its own to play.
            <div className="border border-border-subtle bg-surface-primary px-4 py-4">
              <p className="text-sm text-text-primary">Nothing to play</p>
              <p className="mt-0.5 text-[11px] text-text-secondary">
                {sound.error ?? "This file carries no readable audio header."}
              </p>
            </div>
          )}
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

        {sound.events.length > 0 && (
          <section className="mt-7">
            <h2 className="mb-2 text-[11px] uppercase tracking-wider text-text-dim">
              {sound.events.length === 1 ? "Played by" : `Played by ${sound.events.length} events`}
            </h2>
            <ul className="space-y-3">
              {sound.events.map((e) => (
                <li key={e.package} className="border-l border-border-subtle pl-3">
                  <p className="truncate font-mono text-xs text-mjolnir-gold">{e.name}</p>
                  <p className="truncate font-mono text-[10px] text-text-dim">{e.package}</p>
                  {e.sources.length > 0 && (
                    <details className="mt-1">
                      {/* Which source this particular media is cannot be told
                          from the package, so they are offered as a set. */}
                      <summary className="cursor-pointer font-mono text-[10px] text-text-secondary">
                        {e.sources.length} authored source
                        {e.sources.length === 1 ? "" : "s"}
                      </summary>
                      <ul className="mt-1 space-y-0.5">
                        {e.sources.map((s) => (
                          <li key={s} className="truncate font-mono text-[10px] text-text-dim">
                            {s.replace(/\\/g, "/")}
                          </li>
                        ))}
                      </ul>
                    </details>
                  )}
                </li>
              ))}
            </ul>
          </section>
        )}
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
