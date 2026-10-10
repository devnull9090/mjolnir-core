/**
 * Links that hand off to the desktop launcher through its `mjolnir://`
 * scheme (docs/map_distribution.md): `mjolnir://join/<lobby id>`,
 * `mjolnir://map/<CODE>` and `mjolnir://mod/<slug>`. Launcher 0.13.0 and
 * newer register the scheme; on an older install, or none, the browser
 * simply has nowhere to send it, so every one of these says what it opens.
 *
 * Plain anchors rather than next/link: the router has no business with a
 * custom scheme.
 */
import { LogIn } from "lucide-react";

export const LAUNCHER_LINK_TITLE = "Opens the MJOLNIR launcher (0.13.0 or newer)";

/** Join a listed game: the launcher starts the game and joins it. */
export function JoinButton({ lobbyId, full = false }: { lobbyId: string; full?: boolean }) {
  const shape =
    "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold whitespace-nowrap";
  if (full) {
    return (
      <span
        aria-disabled="true"
        title="This game is full."
        className={`${shape} border border-border text-text-dim cursor-not-allowed`}
      >
        <LogIn className="w-3 h-3" />
        Full
      </span>
    );
  }
  return (
    <a
      href={`mjolnir://join/${encodeURIComponent(lobbyId)}`}
      title={`${LAUNCHER_LINK_TITLE} and joins this game.`}
      className={`${shape} bg-gold/10 text-gold hover:bg-gold/20 transition-colors`}
    >
      <LogIn className="w-3 h-3" />
      Join
    </a>
  );
}
