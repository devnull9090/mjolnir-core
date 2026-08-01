"use client";

import { useCallback, useEffect, useState } from "react";
import { Star } from "lucide-react";

interface Summary {
  count: number;
  mean: number | null;
  distribution: Record<string, number>;
  mine: number | null;
  reviews: { author: string; score: number; review_md: string; created_at: string }[];
}

export function Rating({ slug }: { slug: string }) {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [hover, setHover] = useState(0);
  const [busy, setBusy] = useState(false);
  const [signedIn, setSignedIn] = useState(false);

  const load = useCallback(() => {
    fetch(`/api/v1/mods/${slug}/ratings`)
      .then((r) => (r.ok ? r.json() : null))
      .then(setSummary)
      .catch(() => {});
  }, [slug]);

  useEffect(() => {
    load();
    fetch("/api/v1/auth/me").then((r) => setSignedIn(r.ok));
  }, [load]);

  const rate = async (score: number) => {
    if (busy) return;
    setBusy(true);
    await fetch(`/api/v1/mods/${slug}/ratings/me`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ score }),
    });
    setBusy(false);
    load();
  };

  if (!summary) return <div className="h-20" />;

  const max = Math.max(1, ...Object.values(summary.distribution));

  return (
    <div className="rounded-lg border border-border p-4 space-y-3">
      <div className="flex items-end gap-2">
        <span className="text-3xl font-black text-foreground">
          {summary.mean === null ? "–" : summary.mean.toFixed(1)}
        </span>
        <span className="text-xs text-text-dim pb-1">
          {summary.count} rating{summary.count === 1 ? "" : "s"}
        </span>
      </div>

      {/* Distribution */}
      <div className="space-y-1">
        {[5, 4, 3, 2, 1].map((s) => (
          <div key={s} className="flex items-center gap-2 text-[11px] text-text-dim">
            <span className="w-3">{s}</span>
            <div className="flex-1 h-1.5 rounded bg-surface-card overflow-hidden">
              <div
                className="h-full bg-gold/70"
                style={{ width: `${((summary.distribution[String(s)] ?? 0) / max) * 100}%` }}
              />
            </div>
          </div>
        ))}
      </div>

      {/* Rate */}
      {signedIn ? (
        <div className="pt-1">
          <p className="text-[11px] text-text-dim mb-1">
            {summary.mine ? `Your rating: ${summary.mine}★ — click to change` : "Rate this mod"}
          </p>
          <div className="flex gap-1" onMouseLeave={() => setHover(0)}>
            {[1, 2, 3, 4, 5].map((s) => (
              <button
                key={s}
                disabled={busy}
                aria-label={`${s} star${s === 1 ? "" : "s"}`}
                onMouseEnter={() => setHover(s)}
                onClick={() => rate(s)}
              >
                <Star
                  className={`w-5 h-5 transition-colors ${
                    s <= (hover || summary.mine || 0)
                      ? "fill-gold text-gold"
                      : "text-text-dim"
                  }`}
                />
              </button>
            ))}
          </div>
        </div>
      ) : (
        <p className="text-[11px] text-text-dim">Sign in to rate.</p>
      )}

      {/* Reviews */}
      {summary.reviews.length > 0 && (
        <div className="pt-2 border-t border-border/50 space-y-2">
          {summary.reviews.slice(0, 3).map((r, i) => (
            <div key={i} className="text-xs">
              <span className="text-foreground font-medium">{r.author}</span>{" "}
              <span className="text-gold">{"★".repeat(r.score)}</span>
              <p className="text-text-muted mt-0.5">{r.review_md}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
