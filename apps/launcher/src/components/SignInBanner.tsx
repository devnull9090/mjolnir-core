/**
 * The launcher's hub sign-in, checked at startup and after every sign-in.
 *
 * The game reads the same sign-in for public multiplayer games: listing a
 * game needs `lobbies:write`, and finding one needs any working key
 * (docs/multiplayer_servers.md). A key that is missing, expired, revoked or
 * too old to list games still lets the launcher install mods, so nothing
 * here blocks; it says what is wrong, once, with the button that fixes it.
 *
 * The check runs in Rust (`hub_session_check`), with the key, against
 * /account/me. When the hub cannot be reached the banner stays quiet.
 */
import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { useHub } from "@mjolnir/hub-kit";

interface HubSession {
  state: "signed_out" | "ok" | "expired" | "missing_scope" | "offline";
  expires_at: string | null;
  missing_scopes: string[];
}

/** A sign-in this close to expiring gets a reminder. */
const EXPIRY_WARNING_DAYS = 14;
/** "Not now" on the signed-out prompt, remembered per machine. */
const DISMISSED_KEY = "mjolnir.signInBanner.dismissed";

function readDismissed(): boolean {
  try {
    return localStorage.getItem(DISMISSED_KEY) === "1";
  } catch {
    return false;
  }
}

function writeDismissed() {
  try {
    localStorage.setItem(DISMISSED_KEY, "1");
  } catch {
    // Private storage off: the prompt comes back next start, which is fine.
  }
}

function daysUntil(iso: string | null): number | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  return Number.isNaN(t) ? null : (t - Date.now()) / 86_400_000;
}

export default function SignInBanner() {
  const { user, signIn } = useHub();
  const [session, setSession] = useState<HubSession | null>(null);
  const [dismissed, setDismissed] = useState(readDismissed);
  // Hidden for this run only: the warnings about a broken sign-in return next start.
  const [hidden, setHidden] = useState(false);

  // Again whenever the account changes: signing in, signing out.
  useEffect(() => {
    let live = true;
    invoke<HubSession>("hub_session_check")
      .then((s) => {
        if (live) setSession(s);
      })
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [user?.id]);

  if (!session || hidden) return null;

  let message: string | null = null;
  let action = "Sign in again";
  switch (session.state) {
    case "signed_out":
      if (dismissed) return null;
      message = "Sign in to the MJOLNIR hub to host and join public multiplayer games, rate mods and comment.";
      action = "Sign in";
      break;
    case "expired":
      message = "Your hub sign-in has expired or was revoked. Public multiplayer games need it.";
      break;
    case "missing_scope":
      message = "Your hub sign-in is from before public games. Sign in again to list your games.";
      break;
    case "ok": {
      const days = daysUntil(session.expires_at);
      if (days === null || days >= EXPIRY_WARNING_DAYS) return null;
      message = `Your hub sign-in expires ${
        days < 1 ? "today" : `in ${Math.ceil(days)} day${Math.ceil(days) === 1 ? "" : "s"}`
      }. Sign in again to keep public multiplayer games working.`;
      break;
    }
    default:
      return null;
  }

  return (
    <div className="bg-accent-blue/10 border-b border-accent-blue/30 px-6 py-2.5 flex items-center justify-between gap-4">
      <div className="flex items-center gap-3">
        <span className="w-2 h-2 rounded-full bg-accent-blue" />
        <span className="text-xs text-text-primary">{message}</span>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <button
          onClick={signIn}
          className="px-3 py-1 rounded bg-accent-blue text-white text-xs font-bold hover:brightness-110 transition-all cursor-pointer"
        >
          {action}
        </button>
        <button
          onClick={() => {
            if (session.state === "signed_out") {
              writeDismissed();
              setDismissed(true);
            } else {
              setHidden(true);
            }
          }}
          className="px-2 py-1 rounded text-xs text-text-secondary hover:text-text-primary hover:bg-surface-hover transition-all cursor-pointer"
        >
          Not now
        </button>
      </div>
    </div>
  );
}
