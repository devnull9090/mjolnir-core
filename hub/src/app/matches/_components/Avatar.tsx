import type { MatchPlayer } from "@/lib/api/matches";

/**
 * A seat's face: the linked hub account's Discord avatar, or the in-game
 * name's first letter for a seat no account has claimed.
 */
export function Avatar({ name, user, size = "w-6 h-6" }: { name: string; user: MatchPlayer["user"]; size?: string }) {
  if (user?.avatar_url) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img src={user.avatar_url} alt="" className={`${size} shrink-0 rounded-full border border-border`} />
    );
  }
  return (
    <span
      aria-hidden
      className={`${size} shrink-0 inline-flex items-center justify-center rounded-full border border-border bg-surface-raised text-[10px] font-bold uppercase text-text-dim`}
    >
      {name.trim().charAt(0) || "?"}
    </span>
  );
}
