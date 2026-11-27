"use client";

/**
 * The signed-in account: the name and avatar the hub shows for you (on mod
 * pages, in public games, in game over your Steam or Xbox name), and the
 * one way to change them, which is to change them on Discord and refresh.
 *
 * There is no rename box on purpose: names appear in player reports, so the
 * hub name is always the Discord one. Refreshing is a fresh Discord sign-in
 * (the hub keeps no Discord token to ask with); the callback rewrites the
 * name and avatar and sends you back here.
 */
import Link from "next/link";
import { KeyRound, RefreshCw, UserRound } from "lucide-react";

import { useHub } from "../components/HubKit";
import { PageShell } from "../components/ui";

const REFRESH_HREF = "/api/v1/auth/discord?next=/account";

export default function AccountPage() {
  const { user, ready } = useHub();

  return (
    <PageShell width="2xl">
      <h1 className="flex items-center gap-3 text-3xl font-black text-foreground mb-2">
        <UserRound className="w-7 h-7 text-gold" />
        Account
      </h1>
      <p className="text-text-muted text-sm mb-8">
        Your hub name and avatar come from Discord. Other players see them on your mods, in public games, and in
        game in place of your Steam or Xbox name.
      </p>

      {ready && !user && (
        <div className="rounded-xl border border-border p-8 text-center">
          <p className="text-text-muted mb-4">Sign in to see your account.</p>
          <a
            href={REFRESH_HREF}
            className="inline-block px-4 py-2 text-sm font-semibold rounded-lg bg-[#5865F2] text-white hover:brightness-110"
          >
            Sign in with Discord
          </a>
        </div>
      )}

      {user && (
        <>
          <div className="rounded-xl border border-border p-5 mb-8 flex flex-wrap items-center gap-4">
            {user.avatar_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={user.avatar_url} alt="" crossOrigin="anonymous" className="w-14 h-14 rounded-full" />
            ) : (
              <span className="w-14 h-14 rounded-full bg-surface-raised text-xl font-bold text-foreground flex items-center justify-center">
                {(user.display_name ?? user.username).slice(0, 1).toUpperCase()}
              </span>
            )}
            <div className="flex-1 min-w-0">
              <p className="text-lg font-bold text-foreground truncate">{user.display_name ?? user.username}</p>
              <p className="text-sm text-text-muted truncate">@{user.username} on Discord</p>
            </div>
            <a
              href={REFRESH_HREF}
              title="Sign in with Discord again to pick up your current Discord name and avatar"
              className="flex items-center gap-2 px-4 py-2 text-sm font-semibold rounded-lg bg-[#5865F2] text-white hover:brightness-110"
            >
              <RefreshCw className="w-4 h-4" />
              Refresh from Discord
            </a>
          </div>

          <p className="text-text-muted text-sm mb-8">
            Changed your name or avatar on Discord? Refresh, approve on Discord, and you come back here with the new
            one. Games you start after that show it.
          </p>

          <Link href="/account/keys" className="inline-flex items-center gap-2 text-sm text-gold hover:underline">
            <KeyRound className="w-4 h-4" />
            API keys and signing keys
          </Link>
        </>
      )}
    </PageShell>
  );
}
