import { useEffect, useRef, useState } from "react";
import { ActionButton, useHub } from "@mjolnir/hub-kit";
import { HUB_SITE } from "../hub/client";

/**
 * Who the launcher is signed in as, and how to change that. In the header on
 * every view: the game's public games read the same sign-in, so it is not a
 * Browse Hub detail.
 *
 * Signed in, the header shows only the avatar and name; keys and sign-out sit
 * in a menu behind it, so the header is not a row of small links.
 */
export default function AccountChip() {
  const { user, ready, signIn, signOut, openUrl } = useHub();
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  // Close on a click anywhere else, or on Escape.
  useEffect(() => {
    if (!open) return;
    const onPointer = (e: PointerEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (!ready) return <div className="w-24 h-8" />;

  if (!user) {
    return (
      <ActionButton size="sm" onClick={signIn} title="Needed for public multiplayer games, ratings and comments">
        Sign in to the Hub
      </ActionButton>
    );
  }

  const name = user.display_name ?? user.username;

  return (
    <div ref={root} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        className={`flex items-center gap-2 pl-1 pr-2 py-1 rounded-full border transition-colors duration-150 cursor-pointer
          ${open
            ? "bg-surface-card border-border-subtle"
            : "border-transparent hover:bg-surface-card hover:border-border-subtle"}`}
      >
        {user.avatar_url ? (
          <img src={user.avatar_url} alt="" className="w-6 h-6 rounded-full" />
        ) : (
          <span className="w-6 h-6 rounded-full bg-surface-hover flex items-center justify-center text-xs font-semibold text-text-secondary">
            {name.charAt(0).toUpperCase()}
          </span>
        )}
        <span className="text-sm max-w-32 truncate">{name}</span>
        <svg
          className={`w-3.5 h-3.5 text-text-secondary transition-transform duration-150 ${open ? "rotate-180" : ""}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 top-full mt-2 w-56 z-50 rounded-xl border border-border-subtle bg-surface-card shadow-lg shadow-black/40 py-1"
        >
          <div className="px-3 py-2 border-b border-border-subtle/60">
            <p className="text-sm text-text-primary truncate">{name}</p>
            <p className="text-xs text-text-secondary truncate">Signed in to the Hub as @{user.username}</p>
          </div>
          <button
            role="menuitem"
            onClick={() => {
              setOpen(false);
              openUrl(`${HUB_SITE}/account/keys`);
            }}
            title="Manage or revoke this launcher's access"
            className="w-full flex items-center justify-between px-3 py-2 text-sm text-text-secondary hover:text-text-primary hover:bg-surface-hover cursor-pointer"
          >
            Manage keys
            <span aria-hidden className="text-xs">↗</span>
          </button>
          <button
            role="menuitem"
            onClick={() => {
              setOpen(false);
              signOut();
            }}
            title="Forget this account on this machine"
            className="w-full text-left px-3 py-2 text-sm text-text-secondary hover:text-accent-red hover:bg-surface-hover cursor-pointer"
          >
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
