/**
 * Ratings and reviews for one mod: the score distribution, the caller's own
 * rating, and the most recent written reviews.
 *
 * The same component serves the website's mod page sidebar and the
 * launcher's mod detail pane. Writing needs an identity, which arrives
 * through the provider — in the browser that is a Discord cookie session, in
 * the launcher a paired API key held in Rust.
 */
import { useCallback, useEffect, useState } from "react";

import { HubError } from "../client";
import type { RatingSummary } from "../types";
import { useHub } from "./context";
import { timeAgo } from "./format";
import { StarIcon } from "./icons";
import { ActionButton, ErrorNote, Spinner, StarPicker } from "./primitives";

export function RatingPanel({ slug, compact = false }: { slug: string; compact?: boolean }) {
  const { client, user, signIn } = useHub();
  const [summary, setSummary] = useState<RatingSummary | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [review, setReview] = useState("");
  const [writing, setWriting] = useState(false);

  const load = useCallback(() => {
    client
      .getRatings(slug)
      .then((s) => {
        setSummary(s);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, [client, slug]);

  // The summary carries `mine`, so it is refetched when the identity changes
  // as well as when the mod does.
  useEffect(load, [load, user?.id]);

  const rate = async (score: number, withReview = false) => {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await client.putRating(slug, score, withReview ? review.trim() : undefined);
      if (withReview) {
        setReview("");
        setWriting(false);
      }
      load();
    } catch (e) {
      setError(
        e instanceof HubError && e.needsAuth
          ? "Sign in again — that write was not accepted."
          : e instanceof Error
            ? e.message
            : String(e),
      );
    } finally {
      setBusy(false);
    }
  };

  if (!summary) {
    return (
      <div className="flex items-center gap-2 text-sm text-[var(--mj-text-dim)] h-20">
        {error ? <ErrorNote>{error}</ErrorNote> : <Spinner />}
      </div>
    );
  }

  const max = Math.max(1, ...Object.values(summary.distribution));

  return (
    <div className="rounded-lg border border-[var(--mj-border)] p-4 space-y-3">
      <div className="flex items-end gap-2">
        <span className="text-3xl font-black text-[var(--mj-text)]">
          {summary.mean === null ? "–" : summary.mean.toFixed(1)}
        </span>
        <span className="text-xs text-[var(--mj-text-dim)] pb-1">
          {summary.count} rating{summary.count === 1 ? "" : "s"}
        </span>
      </div>

      <div className="space-y-1">
        {[5, 4, 3, 2, 1].map((s) => (
          <div key={s} className="flex items-center gap-2 text-[11px] text-[var(--mj-text-dim)]">
            <span className="w-3">{s}</span>
            <div className="flex-1 h-1.5 rounded bg-[var(--mj-surface-raised)] overflow-hidden">
              <div
                className="h-full bg-[var(--mj-gold)]/70"
                style={{ width: `${((summary.distribution[String(s)] ?? 0) / max) * 100}%` }}
              />
            </div>
            <span className="w-6 text-right tabular-nums">
              {summary.distribution[String(s)] ?? 0}
            </span>
          </div>
        ))}
      </div>

      {error && <ErrorNote>{error}</ErrorNote>}

      {user ? (
        <div className="pt-1 space-y-2">
          <p className="text-[11px] text-[var(--mj-text-dim)]">
            {summary.mine ? `Your rating: ${summary.mine}★ — click to change` : "Rate this mod"}
          </p>
          <StarPicker value={summary.mine} onRate={(s) => void rate(s)} disabled={busy} />
          {writing ? (
            <div className="space-y-2">
              <textarea
                autoFocus
                value={review}
                onChange={(e) => setReview(e.target.value)}
                rows={3}
                maxLength={8192}
                placeholder="What worked, what broke, what it pairs well with…"
                className="w-full px-3 py-2 text-sm rounded-lg bg-[var(--mj-bg)] border border-[var(--mj-border)] text-[var(--mj-text)] placeholder:text-[var(--mj-text-dim)] focus:border-[var(--mj-gold)]/60 focus:outline-none"
              />
              <div className="flex gap-2">
                <ActionButton
                  size="sm"
                  disabled={busy || !review.trim() || !summary.mine}
                  title={summary.mine ? undefined : "Pick a score first"}
                  onClick={() => void rate(summary.mine ?? 5, true)}
                >
                  Post review
                </ActionButton>
                <ActionButton size="sm" tone="neutral" onClick={() => setWriting(false)}>
                  Cancel
                </ActionButton>
              </div>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setWriting(true)}
              className="text-[11px] text-[var(--mj-text-dim)] hover:text-[var(--mj-text)] cursor-pointer"
            >
              Write a review →
            </button>
          )}
        </div>
      ) : (
        <button
          type="button"
          onClick={signIn}
          className="text-[11px] text-[var(--mj-gold)] hover:underline cursor-pointer"
        >
          Sign in to rate this mod
        </button>
      )}

      {summary.reviews.length > 0 && (
        <div className="pt-2 border-t border-[var(--mj-border)] space-y-3">
          {summary.reviews.slice(0, compact ? 3 : 20).map((r, i) => (
            <div key={`${r.author}-${i}`} className="text-xs">
              <div className="flex items-center gap-2">
                <span className="text-[var(--mj-text)] font-medium">{r.author}</span>
                <span className="inline-flex text-[var(--mj-gold)]" aria-label={`${r.score} of 5`}>
                  {[1, 2, 3, 4, 5].map((s) => (
                    <StarIcon key={s} filled={s <= r.score} className="w-3 h-3" />
                  ))}
                </span>
                <span className="text-[var(--mj-text-dim)]">{timeAgo(r.created_at)}</span>
              </div>
              <p className="text-[var(--mj-text-muted)] mt-0.5 whitespace-pre-wrap break-words">
                {r.review_md}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
