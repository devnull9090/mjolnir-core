"use client";

import Link from "next/link";
import { LogOut, ShieldCheck } from "lucide-react";

import { useHub } from "./HubKit";

/**
 * Discord sign-in / signed-in chip for the navbar. The session comes from
 * the shared hub context mounted in the root layout, so the page makes one
 * `/auth/me` call no matter how many components care about the answer.
 */
export function AuthButton() {
  const { user, ready, signIn, signOut } = useHub();

  if (!ready) return <div className="w-24" />;

  if (!user) {
    return (
      <button
        onClick={signIn}
        className="px-3 py-1.5 text-sm font-semibold rounded-lg border border-[#5865F2]/60 text-[#8b95f6] hover:bg-[#5865F2]/10 transition-colors cursor-pointer"
      >
        Sign in
      </button>
    );
  }

  return (
    <div className="flex items-center gap-2">
      {user.role !== "user" && (
        <Link
          href="/moderation"
          title="Moderation queue"
          className="text-gold hover:brightness-110"
        >
          <ShieldCheck className="w-4 h-4" />
        </Link>
      )}
      {/* The avatar alone: the header has no room for a name beside the
          links, so it is the link's title and label instead. */}
      <Link
        href={`/users/${user.id}`}
        title={user.display_name ?? user.username}
        aria-label={`${user.display_name ?? user.username}: your profile`}
        className="shrink-0 rounded-full hover:ring-2 hover:ring-gold/40 transition-shadow"
      >
        {user.avatar_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={user.avatar_url} alt="" className="w-7 h-7 rounded-full" />
        ) : (
          <span className="w-7 h-7 rounded-full bg-surface-raised text-xs font-bold text-foreground flex items-center justify-center">
            {(user.display_name ?? user.username).slice(0, 1).toUpperCase()}
          </span>
        )}
      </Link>
      <button
        title="Sign out"
        aria-label="Sign out"
        onClick={signOut}
        className="text-text-muted hover:text-foreground cursor-pointer"
      >
        <LogOut className="w-4 h-4" />
      </button>
    </div>
  );
}
