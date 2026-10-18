"use client";

/**
 * Players' /bench runs (docs/performance.md): what the remastered maps cost
 * on their PCs, by GPU, resolution and foliage quality.
 *
 * Admins only: a report names the account that sent it, with its GPU and
 * CPU. The averages leave out runs from a player's first two minutes on a
 * map, while shaders and textures still load.
 */
import { useCallback, useEffect, useState } from "react";

import type { BenchReport, BenchSummaryRow, HubClient } from "@mjolnir/hub-kit";

const QUALITY = ["Low", "Medium", "High", "Epic", "Cinematic"];

function fps(ms: number) {
  return Math.round(1000 / ms);
}

function quality(q: number | null | undefined) {
  return q === null || q === undefined ? "?" : (QUALITY[q] ?? String(q));
}

function cost(delta: number | null, base: number) {
  if (delta === null) return "–";
  return `${(-delta).toFixed(1)} ms (${Math.round((-delta * 100) / base)}%)`;
}

function when(sql: string) {
  return sql.slice(0, 16).replace("T", " ");
}

/** The frame time a run saved without `name`; within noise of nothing reads 0.0. */
function saved(b: BenchReport, name: string) {
  const r = b.results.find((x) => x.name === name);
  if (!r) return "–";
  const d = b.base_ms - r.ms;
  return (Math.abs(d) < 0.05 ? 0 : d).toFixed(1);
}

const TH = "px-3 py-2 text-left";
const TD = "px-3 py-2";

export function Benches({ client, onError }: { client: HubClient; onError: (message: string | null) => void }) {
  const [summary, setSummary] = useState<BenchSummaryRow[] | null>(null);
  const [benches, setBenches] = useState<BenchReport[] | null>(null);
  const [next, setNext] = useState<string | null>(null);
  const [gpu, setGpu] = useState("");

  const fail = useCallback((e: unknown) => onError(e instanceof Error ? e.message : String(e)), [onError]);

  const load = useCallback(
    (q: string, before?: string) => {
      client
        .listBenches({ gpu: q || undefined, before })
        .then((r) => {
          setBenches((old) => (before && old ? [...old, ...r.benches] : r.benches));
          setNext(r.next);
        })
        .catch(fail);
    },
    [client, fail],
  );

  useEffect(() => {
    client.benchSummary().then(setSummary).catch(fail);
    load("");
  }, [client, fail, load]);

  return (
    <section>
      <h2 className="text-sm font-bold uppercase text-text-dim mb-3">
        Benchmarks{summary ? ` · ${summary.reduce((n, r) => n + r.reports, 0)} foliage runs averaged` : ""}
      </h2>
      <p className="text-xs text-text-dim mb-4">
        Sent with /bench in match chat: the map with and without its foliage, at the player&apos;s held camera.
      </p>

      {summary === null ? (
        <p className="text-text-dim text-sm">Loading…</p>
      ) : summary.length === 0 ? (
        <p className="text-text-dim text-sm">No benchmarks yet.</p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border mb-6">
          <table className="w-full text-xs">
            <thead className="bg-surface-raised text-text-dim uppercase tracking-wide">
              <tr>
                <th className={TH}>Map</th>
                <th className={TH}>GPU</th>
                <th className={`${TH} text-right`}>Height</th>
                <th className={TH}>Foliage</th>
                <th className={`${TH} text-right`}>Frame rate</th>
                <th className={`${TH} text-right`}>Foliage costs</th>
                <th className={`${TH} text-right`}>Runs</th>
              </tr>
            </thead>
            <tbody>
              {summary.map((r, i) => (
                <tr key={i} className="border-t border-border">
                  <td className={`${TD} text-foreground`}>{r.map_code}</td>
                  <td className={`${TD} text-text-muted`}>{r.gpu_name ?? "Unknown GPU"}</td>
                  <td className={`${TD} text-right text-text-muted`}>{r.viewport_h ? `${r.viewport_h}p` : "?"}</td>
                  <td className={`${TD} text-text-muted`}>{quality(r.foliage_quality)}</td>
                  <td className={`${TD} text-right text-foreground font-semibold`}>
                    {fps(r.base_ms)} fps <span className="font-normal text-text-dim">{r.base_ms.toFixed(1)} ms</span>
                  </td>
                  <td className={`${TD} text-right text-text-muted`}>{cost(r.foliage_delta_ms, r.base_ms)}</td>
                  <td className={`${TD} text-right text-text-dim`}>{r.reports}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <form
        onSubmit={(e) => {
          e.preventDefault();
          load(gpu);
        }}
        className="flex gap-2 mb-3"
      >
        <input
          type="text"
          value={gpu}
          onChange={(e) => setGpu(e.target.value)}
          placeholder="Filter runs by GPU (e.g. 3060)"
          maxLength={80}
          className="flex-1 max-w-sm px-3 py-1.5 rounded-lg border border-border bg-surface text-sm text-foreground placeholder:text-text-dim focus:outline-none focus:border-gold/60"
        />
      </form>

      {benches !== null && benches.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-xs">
            <thead className="bg-surface-raised text-text-dim uppercase tracking-wide">
              <tr>
                <th className={TH}>Sent (UTC)</th>
                <th className={TH}>By</th>
                <th className={TH}>Map</th>
                <th className={TH}>GPU</th>
                <th className={TH}>Drawn at</th>
                <th className={TH}>Foliage</th>
                <th className={`${TH} text-right`}>Frame rate</th>
                <th className={`${TH} text-right`} title="Frame time saved without the foliage, its shadows, its wind">
                  Foliage / shadows / wind (ms)
                </th>
              </tr>
            </thead>
            <tbody>
              {benches.map((b) => (
                <tr key={b.id} className="border-t border-border">
                  <td className={`${TD} text-text-dim whitespace-nowrap`}>{when(b.created_at)}</td>
                  <td className={`${TD} text-text-muted`}>{b.user.name}</td>
                  <td className={`${TD} text-foreground`}>{b.map_code}</td>
                  <td className={`${TD} text-text-muted`} title={b.cpu ?? undefined}>
                    {b.gpu_name ?? "Unknown GPU"}
                  </td>
                  <td className={`${TD} text-text-muted whitespace-nowrap`}>
                    {b.viewport_w && b.viewport_h ? `${b.viewport_w}×${b.viewport_h}` : "?"}
                    {b.screen_percentage && b.screen_percentage !== 100 ? ` at ${b.screen_percentage}%` : ""}
                    {b.window_mode ? `, ${b.window_mode}` : ""}
                  </td>
                  <td className={`${TD} text-text-muted`}>{quality(b.sg.Foliage)}</td>
                  <td className={`${TD} text-right text-foreground font-semibold`}>{fps(b.base_ms)} fps</td>
                  <td className={`${TD} text-right text-text-muted whitespace-nowrap`}>
                    {b.kind === "foliage"
                      ? `${saved(b, "no foliage")} / ${saved(b, "no foliage shadows")} / ${saved(b, "no foliage wind")}`
                      : b.label}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {next && (
        <button onClick={() => load(gpu, next)} className="mt-3 text-sm text-gold hover:underline cursor-pointer">
          Older →
        </button>
      )}
    </section>
  );
}
