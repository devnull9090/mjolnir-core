import { Crown } from "lucide-react";
import { AvatarImage } from "./AvatarImage";

/** The linked hub account a seat may carry. */
export interface SeatUser {
  avatar_url: string | null;
}

const AVATAR_SIZES = {
  xs: "h-5 w-5 text-[9px]",
  sm: "h-6 w-6 text-[10px]",
  md: "h-9 w-9 text-xs",
  lg: "h-14 w-14 text-base",
  xl: "h-20 w-20 text-2xl",
} as const;

/**
 * A seat's face: the linked hub account's Discord avatar, or the in-game
 * name's first letter for a seat no account has claimed. Decorative — it
 * always sits beside the name — so it carries no alt text.
 */
export function PlayerAvatar({
  name,
  user,
  size = "sm",
  ring,
}: {
  name: string;
  user: SeatUser | null;
  size?: keyof typeof AVATAR_SIZES;
  /** A podium place's colour around the face. */
  ring?: 1 | 2 | 3;
}) {
  const box = `${AVATAR_SIZES[size]} relative shrink-0 overflow-hidden rounded-full ${ring ? `ring-2 ${PLACE_RING[ring]}` : "border border-border-bright"}`;
  // The initial always renders; a Discord avatar sits on top of it. A stale
  // avatar hash 404s, and AvatarImage then removes itself, so the initial
  // shows through instead of a broken-image icon.
  return (
    <span aria-hidden className={`${box} inline-flex items-center justify-center bg-surface-hover font-bold uppercase text-foreground/80`}>
      {name.trim().charAt(0) || "?"}
      {user?.avatar_url && (
        <AvatarImage src={user.avatar_url} className="absolute inset-0 h-full w-full object-cover" />
      )}
    </span>
  );
}

const PLACE_RING = { 1: "ring-gold", 2: "ring-silver", 3: "ring-bronze" } as const;
const PLACE_STYLE = {
  1: "bg-gold text-background",
  2: "bg-silver text-background",
  3: "bg-bronze text-background",
} as const;
const ORDINALS = ["1st", "2nd", "3rd"];

export function ordinal(n: number): string {
  if (n >= 1 && n <= 3) return ORDINALS[n - 1];
  const tens = n % 100;
  return `${n}${tens >= 11 && tens <= 13 ? "th" : (["th", "st", "nd", "rd"][n % 10] ?? "th")}`;
}

/**
 * A finishing place. First, second and third are gold, silver and bronze
 * medals; the word is always written, so the colour is never the only cue.
 */
export function PlaceBadge({ place, size = "sm" }: { place: number; size?: "sm" | "md" }) {
  const dims = size === "md" ? "h-8 min-w-8 text-sm" : "h-6 min-w-6 text-[11px]";
  const style = place >= 1 && place <= 3 ? PLACE_STYLE[place as 1 | 2 | 3] : "bg-surface-hover text-foreground";
  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center rounded-full px-1.5 font-black tabular-nums ${dims} ${style}`}
    >
      {ordinal(place)}
    </span>
  );
}

/** "Winner", with a crown: the badge a winning seat or team carries. */
export function WinnerTag({ className = "" }: { className?: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full bg-gold/15 px-2 py-0.5 text-[11px] font-bold uppercase tracking-wide text-gold ${className}`}
    >
      <Crown aria-hidden className="h-3 w-3" />
      Winner
    </span>
  );
}

export const TEAM_TEXT: Record<string, string> = { red: "text-team-red", blue: "text-team-blue" };
export const TEAM_BG: Record<string, string> = { red: "bg-team-red", blue: "bg-team-blue" };
export const TEAM_BORDER: Record<string, string> = { red: "border-l-team-red", blue: "border-l-team-blue" };

/** A team's colour with its name beside it, for colour-blind readers and screen readers alike. */
export function TeamDot({ team, label = false }: { team: string | null; label?: boolean }) {
  if (!team || !TEAM_BG[team]) return null;
  return (
    <span className="inline-flex items-center gap-1.5">
      <span aria-hidden className={`inline-block h-2.5 w-2.5 rounded-full ${TEAM_BG[team]}`} />
      <span className={label ? `capitalize ${TEAM_TEXT[team]}` : "sr-only"}>{team} team</span>
    </span>
  );
}
