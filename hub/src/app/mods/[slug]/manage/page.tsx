"use client";

/**
 * Owner tools for one mod: drag-and-drop screenshots (alt text required
 * before anything uploads) and the release pipeline — create version,
 * drop the .mjolnir archive, scan, publish. Scan findings render inline
 * so a rejection explains itself.
 */
import { use, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  CheckCircle2,
  ImagePlus,
  Loader2,
  PackagePlus,
  Trash2,
  UploadCloud,
} from "lucide-react";

import { Navbar } from "../../../components/Navbar";
import { Footer } from "../../../components/Footer";

interface Mod {
  id: string;
  slug: string;
  name: string;
}

interface Media {
  id: string;
  url: string;
  alt_text: string;
  kind: "screenshot" | "thumbnail" | "video";
  status: "pending" | "approved" | "rejected";
}

interface Release {
  id: string;
  version: string;
  status: string;
  chunk_count: number;
  findings: { level: string; code: string; message: string }[];
  sha256: string | null;
  file_size: number | null;
}

export default function ManagePage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = use(params);
  const [mod, setMod] = useState<Mod | null | undefined>(undefined);
  const [media, setMedia] = useState<Media[]>([]);
  const [releases, setReleases] = useState<Release[]>([]);
  const [pendingShots, setPendingShots] = useState<{ file: File; alt: string }[]>([]);
  const [version, setVersion] = useState("1.0.0");
  const [banner, setBanner] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const dropRef = useRef<HTMLDivElement>(null);

  const loadMedia = useCallback(
    () =>
      fetch(`/api/v1/mods/${slug}/media`)
        .then((r) => (r.ok ? r.json() : { media: [] }))
        .then((d) => setMedia(d.media)),
    [slug],
  );

  const loadReleases = useCallback(async () => {
    // The public list shows published releases; pending/rejected ones are
    // fetched per-id from sessionStorage so a mid-flow refresh survives.
    const pub = await fetch(`/api/v1/mods/${slug}/releases`)
      .then((r) => (r.ok ? r.json() : { releases: [] }))
      .then((d) => d.releases.map((r: { id: string }) => r.id));
    const mine: string[] = JSON.parse(sessionStorage.getItem(`releases:${slug}`) ?? "[]");
    const ids = [...new Set([...pub, ...mine])];
    const full = await Promise.all(
      ids.map((id) => fetch(`/api/v1/releases/${id}`).then((r) => (r.ok ? r.json() : null))),
    );
    setReleases(full.filter(Boolean));
  }, [slug]);

  // All state updates land asynchronously from fetch resolutions; the rule's
  // static analysis cannot see through the async callees.
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    fetch(`/api/v1/mods/${slug}`)
      .then((r) => (r.ok ? r.json() : null))
      .then(setMod);
    void loadMedia();
    void loadReleases();
  }, [slug, loadMedia, loadReleases]);
  /* eslint-enable react-hooks/set-state-in-effect */

  // ── Screenshots ─────────────────────────────────────────────────────

  const stageFiles = (files: FileList | File[]) => {
    const accepted = [...files].filter((f) =>
      /image\/(png|jpeg|webp)|video\/(mp4|webm)/.test(f.type),
    );
    setPendingShots((p) => [...p, ...accepted.map((file) => ({ file, alt: "" }))]);
  };

  const uploadShot = async (i: number) => {
    const shot = pendingShots[i];
    if (!shot.alt.trim()) return;
    const form = new FormData();
    form.set("file", shot.file);
    form.set("alt_text", shot.alt.trim());
    const res = await fetch(`/api/v1/mods/${slug}/media`, { method: "POST", body: form });
    if (res.ok) {
      setPendingShots((p) => p.filter((_, j) => j !== i));
      loadMedia();
    } else {
      const b = await res.json().catch(() => ({}));
      setBanner(b.message ?? "Upload failed");
    }
  };

  const deleteShot = async (id: string) => {
    await fetch(`/api/v1/media/${id}`, { method: "DELETE" });
    loadMedia();
  };

  // ── Releases ────────────────────────────────────────────────────────

  const createRelease = async () => {
    setBusy(true);
    setBanner(null);
    const res = await fetch(`/api/v1/mods/${slug}/releases`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ version }),
    });
    const body = await res.json().catch(() => ({}));
    if (res.ok) {
      const mine: string[] = JSON.parse(sessionStorage.getItem(`releases:${slug}`) ?? "[]");
      sessionStorage.setItem(`releases:${slug}`, JSON.stringify([...mine, body.id]));
      await loadReleases();
    } else {
      setBanner(body.message ?? body.error ?? "Could not create release");
    }
    setBusy(false);
  };

  const uploadArchive = async (releaseId: string, file: File) => {
    setBusy(true);
    setBanner(null);
    const put = await fetch(`/api/v1/releases/${releaseId}/archive`, {
      method: "PUT",
      headers: { "Content-Type": "application/zip" },
      body: file,
    });
    if (!put.ok) {
      const b = await put.json().catch(() => ({}));
      setBanner(b.message ?? b.error ?? "Archive upload failed");
      setBusy(false);
      return;
    }
    await fetch(`/api/v1/releases/${releaseId}/complete`, { method: "POST" });
    await loadReleases();
    setBusy(false);
  };

  if (mod === undefined) {
    return (
      <>
        <Navbar />
        <main className="pt-40 pb-16 text-center text-text-dim">Loading…</main>
      </>
    );
  }
  if (mod === null) {
    return (
      <>
        <Navbar />
        <main className="pt-40 pb-16 text-center">
          <p className="text-text-muted">
            Not found, or you don&apos;t own this mod.{" "}
            <a href={`/api/v1/auth/discord?next=/mods/${slug}/manage`} className="text-gold hover:underline">
              Sign in
            </a>
          </p>
        </main>
      </>
    );
  }

  return (
    <>
      <Navbar />
      <main className="pt-32 md:pt-36 pb-16 px-6 max-w-3xl mx-auto">
        <p className="text-xs text-text-dim mb-1">
          <Link href={`/mods/${slug}`} className="hover:text-foreground">
            ← {mod.name}
          </Link>
        </p>
        <h1 className="text-3xl font-black text-foreground mb-8">Manage</h1>

        {banner && (
          <div className="mb-6 rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-2 text-sm text-red-300">
            {banner}
          </div>
        )}

        {/* ── Gallery ── */}
        <section className="mb-12">
          <h2 className="text-sm font-bold uppercase text-text-dim mb-3">Gallery</h2>

          <div
            ref={dropRef}
            onDragOver={(e) => {
              e.preventDefault();
              dropRef.current?.classList.add("border-gold/60");
            }}
            onDragLeave={() => dropRef.current?.classList.remove("border-gold/60")}
            onDrop={(e) => {
              e.preventDefault();
              dropRef.current?.classList.remove("border-gold/60");
              stageFiles(e.dataTransfer.files);
            }}
            className="rounded-xl border-2 border-dashed border-border p-8 text-center transition-colors"
          >
            <ImagePlus className="w-8 h-8 text-text-dim mx-auto mb-2" />
            <p className="text-sm text-text-muted">
              Drag screenshots or videos here, or{" "}
              <label className="text-gold hover:underline cursor-pointer">
                browse
                <input
                  type="file"
                  accept="image/png,image/jpeg,image/webp,video/mp4,video/webm"
                  multiple
                  className="hidden"
                  onChange={(e) => e.target.files && stageFiles(e.target.files)}
                />
              </label>
            </p>
            <p className="text-[11px] text-text-dim mt-1">
              png / jpeg / webp ≤ 8 MiB · mp4 / webm ≤ 64 MiB · published after moderator review
            </p>
          </div>

          {/* Staged, awaiting alt text */}
          {pendingShots.map((s, i) => (
            <div key={i} className="mt-3 flex items-center gap-3 rounded-lg border border-border p-3">
              {s.file.type.startsWith("video/") ? (
                <video src={URL.createObjectURL(s.file)} muted className="w-16 h-10 object-cover rounded" />
              ) : (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={URL.createObjectURL(s.file)}
                  alt=""
                  className="w-16 h-10 object-cover rounded"
                />
              )}
              <input
                value={s.alt}
                onChange={(e) =>
                  setPendingShots((p) => p.map((x, j) => (j === i ? { ...x, alt: e.target.value } : x)))
                }
                placeholder="Describe this file (required)"
                className="flex-1 px-3 py-1.5 text-sm rounded-lg bg-background border border-border text-foreground placeholder:text-text-dim focus:border-gold/60 focus:outline-none"
              />
              <button
                onClick={() => uploadShot(i)}
                disabled={!s.alt.trim()}
                className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-gold text-background disabled:opacity-40"
              >
                Upload
              </button>
              <button
                onClick={() => setPendingShots((p) => p.filter((_, j) => j !== i))}
                className="text-text-dim hover:text-red-400"
                aria-label="Discard"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          ))}

          {/* Uploaded */}
          {media.length > 0 && (
            <div className="mt-4 grid grid-cols-3 gap-3">
              {media.map((m) => (
                <figure key={m.id} className="relative group">
                  {m.kind === "video" ? (
                    <video
                      src={m.url}
                      preload="metadata"
                      muted
                      className="rounded-lg border border-border aspect-video object-cover w-full"
                    />
                  ) : (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={m.url}
                      alt={m.alt_text}
                      className="rounded-lg border border-border aspect-video object-cover w-full"
                    />
                  )}
                  {m.status !== "approved" && (
                    <span
                      className={`absolute top-1.5 left-1.5 px-1.5 py-0.5 rounded text-[10px] font-bold uppercase ${
                        m.status === "pending"
                          ? "bg-yellow-500/15 text-yellow-400"
                          : "bg-red-500/15 text-red-400"
                      }`}
                    >
                      {m.status === "pending" ? "awaiting review" : "rejected"}
                    </span>
                  )}
                  <figcaption className="text-[11px] text-text-dim mt-1 truncate" title={m.alt_text}>
                    {m.alt_text}
                  </figcaption>
                  <button
                    onClick={() => deleteShot(m.id)}
                    aria-label={`Delete ${m.alt_text}`}
                    className="absolute top-1.5 right-1.5 p-1 rounded bg-background/80 text-text-dim hover:text-red-400 opacity-0 group-hover:opacity-100 transition-opacity"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </figure>
              ))}
            </div>
          )}
        </section>

        {/* ── Releases ── */}
        <section>
          <h2 className="text-sm font-bold uppercase text-text-dim mb-3">Releases</h2>

          <div className="flex items-center gap-2 mb-4">
            <input
              value={version}
              onChange={(e) => setVersion(e.target.value)}
              pattern="\d+\.\d+\.\d+.*"
              className="w-28 px-3 py-2 text-sm font-mono rounded-lg bg-background border border-border text-foreground focus:border-gold/60 focus:outline-none"
              placeholder="1.0.0"
            />
            <button
              onClick={createRelease}
              disabled={busy}
              className="flex items-center gap-2 px-4 py-2 text-sm font-semibold rounded-lg bg-gold text-background hover:brightness-110 disabled:opacity-40 transition-all"
            >
              <PackagePlus className="w-4 h-4" />
              New release
            </button>
          </div>

          <div className="space-y-3">
            {releases.map((r) => (
              <div key={r.id} className="rounded-lg border border-border p-4">
                <div className="flex items-center justify-between mb-1">
                  <span className="font-mono text-sm text-foreground">v{r.version}</span>
                  <StatusChip status={r.status} />
                </div>

                {(r.status === "pending" || r.status === "rejected") && (
                  <label className="mt-2 flex items-center justify-center gap-2 rounded-lg border border-dashed border-border px-4 py-3 text-sm text-text-muted cursor-pointer hover:border-gold/50 transition-colors">
                    {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <UploadCloud className="w-4 h-4" />}
                    {r.status === "rejected" ? "Upload a fixed .mjolnir archive" : "Drop or choose the .mjolnir archive"}
                    <input
                      type="file"
                      accept=".mjolnir,.zip"
                      className="hidden"
                      onChange={(e) => e.target.files?.[0] && uploadArchive(r.id, e.target.files[0])}
                    />
                  </label>
                )}

                {r.status === "published" && (
                  <p className="text-[11px] text-text-dim mt-1">
                    {r.chunk_count} chunk{r.chunk_count === 1 ? "" : "s"} indexed
                    {r.sha256 ? ` · sha256 ${r.sha256.slice(0, 16)}…` : ""}
                  </p>
                )}

                {r.findings.length > 0 && (
                  <ul className="mt-2 space-y-1">
                    {r.findings.map((f, i) => (
                      <li key={i} className="flex items-start gap-2 text-xs">
                        <AlertTriangle
                          className={`w-3.5 h-3.5 mt-0.5 shrink-0 ${
                            f.level === "error" ? "text-red-400" : "text-yellow-400"
                          }`}
                        />
                        <span className="text-text-muted">
                          <span className="font-mono text-text-dim">{f.code}</span> {f.message}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>

          <p className="text-[11px] text-text-dim mt-4">
            Archive format:{" "}
            <Link href="/docs/notes/mjolnir-format" className="text-gold hover:underline">
              the .mjolnir spec
            </Link>
            . Your first published release takes the mod live.
          </p>
        </section>
      </main>
      <Footer />
    </>
  );
}

function StatusChip({ status }: { status: string }) {
  const styles: Record<string, string> = {
    published: "border-green-500/40 text-green-400",
    pending: "border-border text-text-dim",
    rejected: "border-red-500/40 text-red-400",
    yanked: "border-yellow-500/40 text-yellow-400",
  };
  return (
    <span
      className={`flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold uppercase border ${styles[status] ?? styles.pending}`}
    >
      {status === "published" && <CheckCircle2 className="w-3 h-3" />}
      {status}
    </span>
  );
}
