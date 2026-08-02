"use client";

import { LogOut } from "lucide-react";

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
      {user.avatar_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={user.avatar_url} alt="" className="w-7 h-7 rounded-full" />
      ) : null}
      <span className="text-sm text-foreground font-medium max-w-28 truncate">
        {user.display_name ?? user.username}
      </span>
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
