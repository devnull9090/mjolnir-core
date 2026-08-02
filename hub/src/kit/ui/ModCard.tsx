/**
 * One mod, as a card. The website links its cards to the mod page; the
 * launcher opens a detail pane and hangs an Install button off the same
 * card, so the card takes either an `href` or an `onSelect`, plus an
 * optional action slot.
 */
import type { ReactNode } from "react";

import type { Mod } from "../types";
import { formatCount } from "./format";
import { DownloadIcon } from "./icons";
import { Badge, Stars, TypeBadge } from "./primitives";

export function ModCard({
  mod,
  href,
  onSelect,
  action,
  badges,
  selected = false,
}: {
  mod: Mod;
  href?: string;
  onSelect?: () => void;
  /** Right-hand slot: Install/Update in the launcher, nothing on the web. */
  action?: ReactNode;
  /** Extra badges, e.g. "installed" or a conflict marker. */
  badges?: ReactNode;
  selected?: boolean;
}) {
  const body = (
    <>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-semibold text-[var(--mj-text)] truncate">{mod.name}</span>
          <TypeBadge type={mod.type} />
          <Badge>{mod.category}</Badge>
          {mod.nsfw && <Badge tone="red">nsfw</Badge>}
          {badges}
        </div>
        <p className="text-sm text-[var(--mj-text-muted)] mt-1 line-clamp-2">
          {mod.summary ?? "No summary."}
        </p>
        <div className="flex items-center gap-3 mt-2 text-xs text-[var(--mj-text-dim)]">
          <span className="truncate">by {mod.author}</span>
          <span className="inline-flex items-center gap-1">
            <DownloadIcon className="w-3 h-3" />
            {formatCount(mod.download_count)}
          </span>
          <Stars value={mod.rating_mean} count={mod.rating_count} />
        </div>
      </div>
      {action && (
        // The card as a whole is clickable; the action inside it is its own
        // control, so its clicks must not also open the detail view.
        <div
          className="shrink-0 flex items-center"
          onClick={(e) => e.stopPropagation()}
          onKeyDown={(e) => e.stopPropagation()}
        >
          {action}
        </div>
      )}
    </>
  );

  const className = `w-full text-left bg-[var(--mj-surface)] border rounded-xl p-4 flex items-start gap-3 transition-colors ${
    selected
      ? "border-[var(--mj-gold)]/60"
      : "border-[var(--mj-border)] hover:border-[var(--mj-gold)]/40"
  }`;

  if (href) {
    return (
      <a href={href} className={className}>
        {body}
      </a>
    );
  }
  if (onSelect) {
    return (
      <div
        role="button"
        tabIndex={0}
        onClick={onSelect}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onSelect();
          }
        }}
        className={`${className} cursor-pointer`}
      >
        {body}
      </div>
    );
  }
  return <div className={className}>{body}</div>;
}
