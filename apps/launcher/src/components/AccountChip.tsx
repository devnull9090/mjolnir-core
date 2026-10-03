import { ActionButton, useHub } from "@mjolnir/hub-kit";
import { HUB_SITE } from "../hub/client";

/**
 * Who the launcher is signed in as, and how to change that. In the header on
 * every view: the game's public games read the same sign-in, so it is not a
 * Browse Hub detail.
 */
export default function AccountChip() {
  const { user, ready, signIn, signOut, openUrl } = useHub();

  if (!ready) return <div className="w-24 h-8" />;

  if (!user) {
    return (
      <ActionButton size="sm" onClick={signIn} title="Needed for public multiplayer games, ratings and comments">
        Sign in to the Hub
      </ActionButton>
    );
  }

  return (
    <div className="flex items-center gap-2">
      {user.avatar_url && <img src={user.avatar_url} alt="" className="w-6 h-6 rounded-full" />}
      <span className="text-sm max-w-32 truncate">{user.display_name ?? user.username}</span>
      <button
        onClick={() => openUrl(`${HUB_SITE}/account/keys`)}
        title="Manage or revoke this launcher's access"
        className="text-xs text-text-secondary hover:text-text-primary cursor-pointer"
      >
        keys ↗
      </button>
      <button
        onClick={signOut}
        title="Forget this account on this machine"
        className="text-xs text-text-secondary hover:text-accent-red cursor-pointer"
      >
        Sign out
      </button>
    </div>
  );
}
