import Link from "next/link";
import { Gauge } from "lucide-react";
import { getCloudflareContext } from "@opennextjs/cloudflare";

import { Navbar } from "../components/Navbar";
import { Footer } from "../components/Footer";
import { benchSummary, listBenches, type Bench, type BenchSummaryRow } from "@/lib/api/benches";
import { listMaps } from "@/lib/api/maps";
import { marketingMetadata } from "@/lib/marketing";
import { LocalTime } from "../matches/_components/LocalTime";

export const metadata = marketingMetadata(
  "Halo Campaign Evolved Benchmarks | MJOLNIR Core",
  "Frame rates players measured on the remastered classic Halo CE maps, by GPU, resolution and foliage quality: what the grass costs on a card like yours.",
  "/benchmarks",
);

// Live data: never cached.
export const dynamic = "force-dynamic";

const QUALITY = ["Low", "Medium", "High", "Epic", "Cinematic"];

function fps(ms: number) {
  return Math.round(1000 / ms);
}

function quality(q: number | null | undefined) {
  return q === null || q === undefined ? "?" : (QUALITY[q] ?? String(q));
}

function share(delta: number | null, base: number) {
  if (delta === null) return "–";
  return `${(-delta).toFixed(1)} ms (${Math.round((-delta * 100) / base)}%)`;
}

function resolution(w: number | null, h: number | null) {
  return w && h ? `${w}×${h}` : h ? `${h}p` : "?";
}

function SummaryTable({ rows, mapTitle }: { rows: BenchSummaryRow[]; mapTitle: (code: string) => string }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-border">
      <table className="w-full text-sm">
        <thead className="bg-surface-raised text-text-dim text-xs uppercase tracking-wide">
          <tr>
            <th className="text-left px-4 py-3">Map</th>
            <th className="text-left px-4 py-3">GPU</th>
            <th className="text-right px-4 py-3">Height</th>
            <th className="text-left px-4 py-3">Foliage</th>
            <th className="text-right px-4 py-3">Frame rate</th>
            <th className="text-right px-4 py-3">Foliage costs</th>
            <th className="text-right px-4 py-3">Runs</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-border hover:bg-surface-raised/50">
              <td className="px-4 py-3 text-foreground">{mapTitle(r.map_code)}</td>
              <td className="px-4 py-3 text-text-muted">{r.gpu_name ?? "Unknown GPU"}</td>
              <td className="px-4 py-3 text-right text-text-muted">{r.viewport_h ? `${r.viewport_h}p` : "?"}</td>
              <td className="px-4 py-3 text-text-muted">{quality(r.foliage_quality)}</td>
              <td className="px-4 py-3 text-right font-semibold text-foreground">
                {fps(r.base_ms)} fps <span className="text-xs font-normal text-text-dim">{r.base_ms.toFixed(1)} ms</span>
              </td>
              <td className="px-4 py-3 text-right text-text-muted">{share(r.foliage_delta_ms, r.base_ms)}</td>
              <td className="px-4 py-3 text-right text-text-dim">{r.reports}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RecentTable({ benches, mapTitle }: { benches: Bench[]; mapTitle: (code: string) => string }) {
  const part = (b: Bench, name: string) => {
    const r = b.results.find((x) => x.name === name);
    // Within noise of nothing reads 0.0, not -0.0.
    return r ? (Math.abs(b.base_ms - r.ms) < 0.05 ? 0 : b.base_ms - r.ms).toFixed(1) : "–";
  };
  return (
    <div className="overflow-x-auto rounded-xl border border-border">
      <table className="w-full text-sm">
        <thead className="bg-surface-raised text-text-dim text-xs uppercase tracking-wide">
          <tr>
            <th className="text-left px-4 py-3">Sent</th>
            <th className="text-left px-4 py-3">Map</th>
            <th className="text-left px-4 py-3">GPU</th>
            <th className="text-left px-4 py-3">Drawn at</th>
            <th className="text-left px-4 py-3">Foliage</th>
            <th className="text-right px-4 py-3">Frame rate</th>
            <th className="text-right px-4 py-3" title="Frame time saved without the foliage, its shadows, its wind">
              Foliage / shadows / wind (ms)
            </th>
          </tr>
        </thead>
        <tbody>
          {benches.map((b) => (
            <tr key={b.id} className="border-t border-border hover:bg-surface-raised/50">
              <td className="px-4 py-3 text-text-muted whitespace-nowrap">
                <LocalTime sql={b.created_at} />
              </td>
              <td className="px-4 py-3 text-foreground">{mapTitle(b.map_code)}</td>
              <td className="px-4 py-3 text-text-muted">{b.gpu_name ?? "Unknown GPU"}</td>
              <td className="px-4 py-3 text-text-muted whitespace-nowrap">
                {resolution(b.viewport_w, b.viewport_h)}
                {b.screen_percentage && b.screen_percentage !== 100 ? ` at ${b.screen_percentage}%` : ""}
                {b.window_mode ? `, ${b.window_mode}` : ""}
              </td>
              <td className="px-4 py-3 text-text-muted">{quality(b.sg.Foliage)}</td>
              <td className="px-4 py-3 text-right font-semibold text-foreground">{fps(b.base_ms)} fps</td>
              <td className="px-4 py-3 text-right text-text-muted whitespace-nowrap">
                {b.kind === "foliage"
                  ? `${part(b, "no foliage")} / ${part(b, "no foliage shadows")} / ${part(b, "no foliage wind")}`
                  : b.label}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default async function BenchmarksPage({
  searchParams,
}: {
  searchParams: Promise<{ map?: string; gpu?: string; before?: string }>;
}) {
  const params = await searchParams;
  const map = /^[A-Z0-9]{3}$/.test(params.map ?? "") ? params.map : undefined;
  const gpu = (params.gpu ?? "").trim().slice(0, 80) || undefined;
  const before = /^[\d\- :]{10,19}$/.test(params.before ?? "") ? params.before : undefined;

  const { env } = getCloudflareContext();
  const [summary, { benches, next }, maps] = await Promise.all([
    benchSummary(env.DB as never, { map }),
    listBenches(env.DB as never, { map, gpu, before }),
    listMaps(env.DB as never),
  ]);
  const titles = new Map(maps.map((m) => [m.code, m.title]));
  const mapTitle = (code: string) => titles.get(code) ?? code;
  const benched = new Set(summary.map((r) => r.map_code));

  const qs = (over: Record<string, string | undefined>) => {
    const u = new URLSearchParams();
    for (const [k, v] of Object.entries({ map, gpu, ...over })) if (v) u.set(k, v);
    const s = u.toString();
    return s ? `/benchmarks?${s}` : "/benchmarks";
  };
  const chip = (active: boolean) =>
    `px-3 py-1.5 rounded-full border transition-colors ${
      active ? "border-gold/60 text-gold bg-gold/10" : "border-border text-text-muted hover:text-foreground"
    }`;

  return (
    <>
      <Navbar />

      <main className="marketing pt-40 md:pt-44 pb-16 px-6 max-w-6xl mx-auto">
        <div className="mb-8">
          <h1 className="text-4xl font-black text-foreground mb-3">Benchmarks</h1>
          <p className="text-text-muted text-lg max-w-3xl">
            Frame rates players measured on the remastered maps, and what the grass and other foliage costs, by
            GPU and settings. Type <code className="text-gold">/bench</code> in match chat to add yours: the game
            holds your camera for about a minute, times the map with and without its foliage, and sends the result
            here. Reports are listed by GPU, never by player.
          </p>
          <form action="/benchmarks" className="mt-4 flex items-center gap-2">
            {map && <input type="hidden" name="map" value={map} />}
            <input
              name="gpu"
              defaultValue={gpu}
              placeholder="Find a GPU (e.g. 3060)"
              maxLength={80}
              className="px-3 py-1.5 rounded-full border border-border bg-surface text-sm text-foreground placeholder:text-text-dim focus:outline-none focus:border-gold/60"
            />
          </form>
        </div>

        <div className="mb-8 flex flex-wrap items-center gap-1 text-xs">
          <Link href={qs({ map: undefined, before: undefined })} className={chip(!map)}>
            All maps
          </Link>
          {maps
            .filter((m) => benched.has(m.code) || m.code === map)
            .map((m) => (
              <Link key={m.code} href={qs({ map: m.code, before: undefined })} className={chip(map === m.code)}>
                {m.title}
              </Link>
            ))}
        </div>

        {summary.length === 0 && benches.length === 0 ? (
          <div className="flex items-center gap-3 text-text-muted">
            <Gauge className="w-5 h-5" />
            <p>No benchmarks yet. Type /bench in match chat on a remastered map to send the first.</p>
          </div>
        ) : (
          <>
            {summary.length > 0 && (
              <section className="mb-12">
                <h2 className="text-sm font-bold uppercase text-text-dim mb-3">Averages</h2>
                <SummaryTable rows={summary} mapTitle={mapTitle} />
                <p className="mt-2 text-xs text-text-dim">
                  Runs taken in the first two minutes on a map are left out: the game is still loading shaders
                  and textures then.
                </p>
              </section>
            )}
            <section>
              <h2 className="text-sm font-bold uppercase text-text-dim mb-3">Recent runs</h2>
              <RecentTable benches={benches} mapTitle={mapTitle} />
              {(before || next) && (
                <div className="mt-6 flex gap-4 text-sm">
                  {before && (
                    <Link href={qs({ before: undefined })} className="text-text-muted hover:text-foreground">
                      ← Newest
                    </Link>
                  )}
                  {next && (
                    <Link href={qs({ before: next })} className="text-gold hover:underline">
                      Older →
                    </Link>
                  )}
                </div>
              )}
            </section>
          </>
        )}
      </main>

      <Footer />
    </>
  );
}
