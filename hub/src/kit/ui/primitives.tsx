/** The small pieces every other shared component is built out of. */
import type { ReactNode } from "react";
import { useState } from "react";

import { AlertIcon, ShieldIcon, StarIcon } from "./icons";

export type Tone = "neutral" | "gold" | "green" | "red" | "amber" | "blue";

const TONE_CLASS: Record<Tone, string> = {
  neutral: "bg-[var(--mj-surface-hover)] text-[var(--mj-text-muted)]",
  gold: "bg-[var(--mj-gold)]/15 text-[var(--mj-gold)]",
  green: "bg-[var(--mj-green)]/15 text-[var(--mj-green)]",
  red: "bg-[var(--mj-red)]/15 text-[var(--mj-red)]",
  amber: "bg-[var(--mj-amber)]/15 text-[var(--mj-amber)]",
  blue: "bg-[var(--mj-blue)]/15 text-[var(--mj-blue)]",
};

export function Badge({
  tone = "neutral",
  title,
  className = "",
  children,
}: {
  tone?: Tone;
  title?: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 shrink-0 rounded px-1.5 py-0.5 text-[11px] font-medium ${TONE_CLASS[tone]} ${className}`}
    >
      {children}
    </span>
  );
}

/**
 * Trust tier as a badge. `content` mods are inert data anyone may upload;
 * `script` and `native` execute and therefore only ever come from the
 * signed, reviewed set — worth saying on every card that shows one.
 */
export function TypeBadge({ type }: { type: "content" | "script" | "native" }) {
  if (type === "content") {
    return (
      <Badge tone="neutral" title="Game data only — scanned at upload, cannot execute code.">
        data
      </Badge>
    );
  }
  return (
    <Badge
      tone="blue"
      title="Executes code. Ships only from the reviewed, Ed25519-signed mjolnir-core set."
    >
      <ShieldIcon className="w-3 h-3" />
      {type === "script" ? "signed script" : "signed native"}
    </Badge>
  );
}

/** Verification state of something already on disk. */
export function VerifiedBadge({ ok, detail }: { ok: boolean; detail: string }) {
  return ok ? (
    <Badge tone="green" title={detail}>
      <ShieldIcon className="w-3 h-3" />
      verified
    </Badge>
  ) : (
    <Badge tone="red" title={detail}>
      <AlertIcon className="w-3 h-3" />
      unverified
    </Badge>
  );
}

export function Stars({
  value,
  count,
  size = "sm",
}: {
  value: number | null;
  count?: number;
  size?: "sm" | "md";
}) {
  const px = size === "sm" ? "w-3.5 h-3.5" : "w-4 h-4";
  if (value === null || count === 0) {
    return <span className="text-xs text-[var(--mj-text-dim)]">No ratings yet</span>;
  }
  return (
    <span className="inline-flex items-center gap-1 text-xs text-[var(--mj-text-muted)]">
      <StarIcon filled className={`${px} text-[var(--mj-gold)]`} />
      {value.toFixed(1)}
      {count !== undefined && <span className="text-[var(--mj-text-dim)]">({count})</span>}
    </span>
  );
}

/** Click-to-rate row; hovering previews the score it would set. */
export function StarPicker({
  value,
  onRate,
  disabled = false,
}: {
  value: number | null;
  onRate: (score: number) => void;
  disabled?: boolean;
}) {
  const [hover, setHover] = useState(0);
  return (
    <div className="flex gap-1" onMouseLeave={() => setHover(0)}>
      {[1, 2, 3, 4, 5].map((s) => (
        <button
          key={s}
          type="button"
          disabled={disabled}
          aria-label={`${s} star${s === 1 ? "" : "s"}`}
          aria-pressed={value === s}
          onMouseEnter={() => setHover(s)}
          onFocus={() => setHover(s)}
          onClick={() => onRate(s)}
          className="disabled:opacity-40 cursor-pointer"
        >
          <StarIcon
            filled={s <= (hover || value || 0)}
            className={`w-5 h-5 transition-colors ${
              s <= (hover || value || 0)
                ? "text-[var(--mj-gold)]"
                : "text-[var(--mj-text-dim)]"
            }`}
          />
        </button>
      ))}
    </div>
  );
}

export function Spinner({ className = "w-4 h-4" }: { className?: string }) {
  return (
    <span
      role="status"
      aria-label="Loading"
      className={`inline-block rounded-full border-2 border-[var(--mj-text-dim)] border-t-transparent animate-spin ${className}`}
    />
  );
}

export function ErrorNote({ children }: { children: ReactNode }) {
  return (
    <p className="flex items-start gap-2 rounded-lg border border-[var(--mj-red)]/40 bg-[var(--mj-red)]/10 px-3 py-2 text-sm text-[var(--mj-red)]">
      <AlertIcon className="w-4 h-4 shrink-0 mt-0.5" />
      <span className="min-w-0">{children}</span>
    </p>
  );
}

/** The one button style shared surfaces use, so actions match everywhere. */
export function ActionButton({
  onClick,
  disabled,
  tone = "gold",
  size = "md",
  title,
  children,
}: {
  onClick?: () => void;
  disabled?: boolean;
  tone?: "gold" | "neutral" | "danger";
  size?: "sm" | "md";
  title?: string;
  children: ReactNode;
}) {
  const tones = {
    gold: "border-[var(--mj-gold)]/40 text-[var(--mj-gold)] hover:bg-[var(--mj-gold)]/10",
    neutral:
      "border-[var(--mj-border-bright)] text-[var(--mj-text-muted)] hover:text-[var(--mj-text)]",
    danger: "border-[var(--mj-red)]/30 text-[var(--mj-red)] hover:bg-[var(--mj-red)]/10",
  };
  const sizes = { sm: "px-2.5 py-1 text-xs", md: "px-3 py-1.5 text-sm" };
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex items-center gap-1.5 rounded-lg border font-medium transition-colors disabled:opacity-40 disabled:cursor-default cursor-pointer ${tones[tone]} ${sizes[size]}`}
    >
      {children}
    </button>
  );
}
