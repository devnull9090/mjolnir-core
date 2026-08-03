import { useEffect, useRef, useState } from "react";
import { api } from "../lib/api";

/** Waveform bar count; each bar is one peak over its slice of the audio. */
const BARS = 220;

type Loaded = {
  src: string;
  via: string;
  /** Peak amplitude per bar, 0..1. Empty until the decode finishes. */
  peaks: number[];
};

/**
 * Play one Wwise sound, with a waveform to scrub through.
 *
 * The backend hands over an Ogg (or a plain WAV for the PCM files); decoding
 * is the webview's own, both for playback and for the peaks drawn here.
 */
export function SoundPlayer({ index }: { index: number }) {
  const audio = useRef<HTMLAudioElement | null>(null);
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [at, setAt] = useState(0);
  const [length, setLength] = useState(0);

  // A new sound invalidates whatever the last one loaded.
  useEffect(() => {
    setLoaded(null);
    setError(null);
    setPlaying(false);
    setAt(0);
    setLength(0);
  }, [index]);

  async function load(): Promise<Loaded | null> {
    setLoading(true);
    setError(null);
    try {
      const audioData = await api.playSound(index);
      const next: Loaded = { src: audioData.src, via: audioData.via, peaks: [] };
      setLoaded(next);
      // Peaks are a nicety; playback must not wait on them or fail with them.
      void peaksOf(audioData.src).then((peaks) => {
        if (peaks) setLoaded((cur) => (cur?.src === next.src ? { ...cur, peaks } : cur));
      });
      return next;
    } catch (e) {
      setError(String(e));
      return null;
    } finally {
      setLoading(false);
    }
  }

  async function onToggle() {
    if (playing) {
      audio.current?.pause();
      return;
    }
    if (!loaded) {
      const next = await load();
      if (!next) return;
      // The element renders with the new src; play once it is mounted.
      queueMicrotask(() => void audio.current?.play().catch(() => setPlaying(false)));
      return;
    }
    void audio.current?.play().catch(() => setPlaying(false));
  }

  function seek(fraction: number) {
    const el = audio.current;
    if (!el || !Number.isFinite(el.duration)) return;
    el.currentTime = Math.max(0, Math.min(1, fraction)) * el.duration;
  }

  const progress = length > 0 ? at / length : 0;

  return (
    <div className="border border-border-subtle bg-surface-primary px-4 py-4">
      <div className="flex items-center gap-4">
        <button
          type="button"
          onClick={() => void onToggle()}
          disabled={loading}
          title={playing ? "Pause" : "Play"}
          aria-label={playing ? "Pause" : "Play"}
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full border border-mjolnir-gold/60 text-mjolnir-gold transition-colors hover:bg-mjolnir-gold/10 disabled:opacity-40"
        >
          {loading ? (
            <span className="text-[10px]">…</span>
          ) : playing ? (
            <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true">
              <path d="M3 2h4v12H3zM9 2h4v12H9z" fill="currentColor" />
            </svg>
          ) : (
            <svg width="16" height="16" viewBox="0 0 16 16" aria-hidden="true">
              <path d="M4 2.5v11l9-5.5-9-5.5z" fill="currentColor" />
            </svg>
          )}
        </button>

        <div className="min-w-0 flex-1">
          <Waveform peaks={loaded?.peaks ?? []} progress={progress} onSeek={seek} />
          <div className="mt-1 flex items-baseline justify-between font-mono text-[10px] text-text-dim">
            <span>
              {length > 0 ? `${clock(at)} / ${clock(length)}` : loaded ? "ready" : "not loaded"}
            </span>
            {loaded && <span>rebuilt via {loaded.via}</span>}
          </div>
        </div>
      </div>

      {error && (
        <p className="mt-2 font-mono text-[11px] text-accent-red">This sound could not be played: {error}</p>
      )}

      {loaded && (
        <audio
          ref={audio}
          src={loaded.src}
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          onEnded={() => setPlaying(false)}
          onTimeUpdate={(e) => setAt(e.currentTarget.currentTime)}
          onDurationChange={(e) =>
            setLength(Number.isFinite(e.currentTarget.duration) ? e.currentTarget.duration : 0)
          }
          className="hidden"
        />
      )}
    </div>
  );
}

/** Seconds as `m:ss`. */
function clock(secs: number): string {
  const m = Math.floor(secs / 60);
  const s = Math.floor(secs % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

/**
 * Peak amplitude per bar, by decoding the stream once with the Web Audio API.
 *
 * Returns null rather than throwing: a missing waveform is cosmetic, and the
 * audio still plays without it.
 */
async function peaksOf(src: string): Promise<number[] | null> {
  try {
    const bytes = await (await fetch(src)).arrayBuffer();
    const ctx = new OfflineAudioContext(1, 1, 44100);
    const buffer = await ctx.decodeAudioData(bytes);
    // Mix the channels down; the waveform is a shape, not a measurement.
    const chans = Array.from({ length: buffer.numberOfChannels }, (_, c) =>
      buffer.getChannelData(c),
    );
    const per = Math.max(1, Math.floor(buffer.length / BARS));
    const peaks: number[] = [];
    for (let b = 0; b < BARS; b++) {
      let peak = 0;
      const start = b * per;
      const end = Math.min(start + per, buffer.length);
      for (let i = start; i < end; i++) {
        let sum = 0;
        for (const ch of chans) sum += ch[i];
        peak = Math.max(peak, Math.abs(sum / chans.length));
      }
      peaks.push(peak);
    }
    const loudest = Math.max(...peaks, 0.0001);
    return peaks.map((p) => p / loudest);
  } catch {
    return null;
  }
}

/** The waveform strip; click or drag anywhere on it to seek. */
function Waveform({
  peaks,
  progress,
  onSeek,
}: {
  peaks: number[];
  progress: number;
  onSeek: (fraction: number) => void;
}) {
  const seekFrom = (e: React.MouseEvent<HTMLDivElement>) => {
    const box = e.currentTarget.getBoundingClientRect();
    onSeek((e.clientX - box.left) / box.width);
  };

  return (
    <div
      className="flex h-12 cursor-pointer items-center gap-px"
      onClick={seekFrom}
      onMouseMove={(e) => e.buttons === 1 && seekFrom(e)}
      role="presentation"
    >
      {peaks.length === 0
        ? // Before the decode lands, a flat rule stands in for the shape.
          <div className="h-px w-full bg-border-subtle" />
        : peaks.map((p, i) => (
            <div
              key={i}
              className={`min-w-0 flex-1 ${
                i / peaks.length <= progress ? "bg-mjolnir-gold" : "bg-text-dim/40"
              }`}
              // A floor keeps silence visible as a line rather than a gap.
              style={{ height: `${Math.max(2, p * 100)}%` }}
            />
          ))}
    </div>
  );
}
