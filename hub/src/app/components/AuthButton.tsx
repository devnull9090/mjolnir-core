"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ChevronDown, KeyRound, LogOut, ShieldCheck, User, UserRound } from "lucide-react";

import { useHub } from "./HubKit";

/**
 * Discord sign-in button when logged out, or a compact avatar dropdown menu
 * when signed in so account, API keys, moderation, and sign-out stay
 * organized without crowding the header bar.
 */
export function AuthButton() {
  const { user, ready, signIn, signOut } = useHub();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: PointerEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  if (!ready) return <div className="h-9 w-[74px]" aria-hidden="true" />;

  if (!user) {
    return (
      <button
        type="button"
        onClick={signIn}
        className="whitespace-nowrap rounded-lg border border-[#5865F2]/60 px-3.5 py-2 text-sm font-semibold text-[#8b95f6] transition-colors hover:bg-[#5865F2]/10 cursor-pointer"
      >
        Sign in
      </button>
    );
  }

  const displayName = user.display_name ?? user.username;
  const isStaff = user.role !== "user";

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        aria-expanded={open}
        aria-haspopup="menu"
        aria-label={`${displayName} account menu`}
        title={displayName}
        className={`group flex items-center gap-1.5 rounded-full border py-1 pl-1 pr-2 transition-all cursor-pointer ${
          open
            ? "border-gold/60 bg-surface-raised ring-2 ring-gold/15"
            : "border-border-bright/80 bg-surface/75 hover:border-gold/45 hover:bg-surface-raised"
        }`}
      >
        <span className="relative block shrink-0">
          {user.avatar_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={user.avatar_url}
              alt=""
              crossOrigin="anonymous"
              className="size-7 rounded-full object-cover"
            />
          ) : (
            <span className="flex size-7 items-center justify-center rounded-full bg-surface-card text-xs font-bold text-foreground">
              {displayName.slice(0, 1).toUpperCase()}
            </span>
          )}
          {isStaff && (
            <span
              aria-hidden="true"
              className="absolute -right-0.5 -top-0.5 flex size-3.5 items-center justify-center rounded-full border border-background bg-gold text-background"
            >
              <ShieldCheck className="size-2.5" strokeWidth={2.75} />
            </span>
          )}
        </span>
        <ChevronDown
          aria-hidden="true"
          className={`size-3.5 text-text-muted transition-transform duration-150 group-hover:text-foreground ${
            open ? "rotate-180 text-gold" : ""
          }`}
        />
      </button>

      {open && (
        <div
          role="menu"
          aria-label="Account menu"
          className="mj-select-menu absolute right-0 top-full z-50 mt-2.5 w-60 rounded-xl border border-border-bright bg-surface/95 p-1.5 shadow-[0_20px_48px_-12px_rgba(0,0,0,0.85)] backdrop-blur-xl"
        >
          {/* Signed-in identity header */}
          <div className="mb-1 flex items-center gap-2.5 border-b border-border px-2.5 pb-2.5 pt-2">
            {user.avatar_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={user.avatar_url}
                alt=""
                crossOrigin="anonymous"
                className="size-8 shrink-0 rounded-full object-cover"
              />
            ) : (
              <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-surface-card text-xs font-bold text-foreground">
                {displayName.slice(0, 1).toUpperCase()}
              </span>
            )}
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.5">
                <p className="truncate text-sm font-semibold text-foreground">{displayName}</p>
                {isStaff && (
                  <span className="shrink-0 rounded bg-gold/15 px-1.5 py-0.5 font-mono text-[9px] font-bold uppercase tracking-wider text-gold">
                    {user.role}
                  </span>
                )}
              </div>
              {user.display_name && user.display_name !== user.username && (
                <p className="truncate text-xs text-text-dim">@{user.username}</p>
              )}
            </div>
          </div>

          <Link
            href={`/users/${user.id}`}
            role="menuitem"
            onClick={() => setOpen(false)}
            className="flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm text-text-muted transition-colors hover:bg-surface-raised hover:text-foreground"
          >
            <User aria-hidden="true" className="size-4 shrink-0" />
            <span>Profile</span>
          </Link>

          {isStaff && (
            <Link
              href="/moderation"
              role="menuitem"
              onClick={() => setOpen(false)}
              className="flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium text-gold transition-colors hover:bg-gold/10"
            >
              <ShieldCheck aria-hidden="true" className="size-4 shrink-0" />
              <span>Moderation queue</span>
            </Link>
          )}

          <Link
            href="/account"
            role="menuitem"
            onClick={() => setOpen(false)}
            className="flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm text-text-muted transition-colors hover:bg-surface-raised hover:text-foreground"
          >
            <UserRound aria-hidden="true" className="size-4 shrink-0" />
            <span>Account</span>
          </Link>

          <Link
            href="/account/keys"
            role="menuitem"
            onClick={() => setOpen(false)}
            className="flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm text-text-muted transition-colors hover:bg-surface-raised hover:text-foreground"
          >
            <KeyRound aria-hidden="true" className="size-4 shrink-0" />
            <span>API keys</span>
          </Link>

          <div className="my-1 border-t border-border" />

          <button
            type="button"
            role="menuitem"
            onClick={() => {
              setOpen(false);
              signOut();
            }}
            className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-sm text-text-muted transition-colors hover:bg-accent-red/10 hover:text-accent-red cursor-pointer"
          >
            <LogOut aria-hidden="true" className="size-4 shrink-0" />
            <span>Sign out</span>
          </button>
        </div>
      )}
    </div>
  );
}
