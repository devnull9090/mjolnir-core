"use client";

/**
 * Approve a desktop client that is waiting to pair.
 *
 * The client shows a code and opens this page with `?code=` filled in; the
 * user confirms here, signed in, and the client's next poll collects a scoped
 * API key. The warning is load-bearing: the only attack this flow has is
 * talking someone into approving a code they did not generate, and this page
 * is where that gets refused.
 *
 * Clients ask for different things — the launcher rates and comments, the tag
 * editor publishes — so what is being granted is read off the pending
 * handshake rather than stated here. Publishing is called out separately
 * because approving it in error costs an account its name on a release, not
 * a comment.
 */
import { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { KeyRound, ShieldAlert, Upload } from "lucide-react";

import { Navbar } from "../components/Navbar";
import { Footer } from "../components/Footer";
import { useHub } from "../components/HubKit";

interface Pending {
  user_code: string;
  client_name: string;
  scopes: string[];
  key_ttl_days: number;
}

/** Plain-language readings of the scopes a device may ask for. */
const SCOPE_LABELS: Record<string, string> = {
  "mods:read": "Browse the hub as you",
  "mods:write": "Publish and update mods in your name",
  "ratings:write": "Rate mods as you",
  "comments:write": "Post comments as you",
};

/** A scope with no reading is still shown — unnamed, but never hidden. */
function describeScope(scope: string): string {
  return SCOPE_LABELS[scope] ?? scope;
}

function normalize(code: string): string {
  return code.trim().toUpperCase();
}

function LinkForm() {
  const { user, ready, signIn } = useHub();
  const searchParams = useSearchParams();
  // The typed value wins once there is one; until then the URL supplies it,
  // so nothing has to be copied into state on mount.
  const [typed, setTyped] = useState<string | null>(null);
  const code = normalize(typed ?? searchParams.get("code") ?? "");

  const [pending, setPending] = useState<Pending | null>(null);
  // The decision is kept with the client it was made about, so the
  // confirmation can name what was linked after `pending` stops mattering.
  const [outcome, setOutcome] = useState<{
    status: "approved" | "denied";
    client_name: string;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Look the code up as it is typed so the page can name what is waiting.
  // The answer is stored with the code it belongs to, which is what keeps a
  // slow response from describing a code the user has since edited.
  useEffect(() => {
    if (code.length < 8) return;
    let live = true;
    fetch(`/api/v1/auth/device/pending/${encodeURIComponent(code)}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((info: Omit<Pending, "user_code"> | null) => {
        if (live) setPending(info ? { user_code: code, ...info } : null);
      })
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [code]);

  const waiting = pending?.user_code === code ? pending : null;
  const publishes = waiting?.scopes.includes("mods:write") ?? false;

  const decide = useCallback(
    async (approve: boolean) => {
      setBusy(true);
      setError(null);
      const res = await fetch("/api/v1/auth/device/approve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_code: code, approve }),
      });
      const body = await res.json().catch(() => ({}));
      if (res.ok) setOutcome({ status: body.status, client_name: body.client_name });
      else setError(body.message ?? body.error ?? "That did not work.");
      setBusy(false);
    },
    [code],
  );

  if (outcome?.status === "approved") {
    return (
      <div className="rounded-xl border border-gold/40 bg-gold/5 p-6">
        <p className="text-foreground font-semibold mb-1">Device linked.</p>
        <p className="text-sm text-text-muted">
          Head back to {outcome.client_name} — it will pick this up within a few seconds. You can
          revoke it any time from{" "}
          <Link href="/account/keys" className="text-gold hover:underline">
            your API keys
          </Link>
          .
        </p>
      </div>
    );
  }

  if (outcome?.status === "denied") {
    return (
      <div className="rounded-xl border border-border p-6">
        <p className="text-foreground font-semibold mb-1">Request denied.</p>
        <p className="text-sm text-text-muted">Nothing was granted.</p>
      </div>
    );
  }

  if (ready && !user) {
    return (
      <div className="rounded-xl border border-border p-8 text-center">
        <p className="text-text-muted mb-4">Sign in to approve a device.</p>
        <button
          onClick={signIn}
          className="px-4 py-2 text-sm font-semibold rounded-lg bg-[#5865F2] text-white hover:brightness-110 cursor-pointer"
        >
          Sign in with Discord
        </button>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-border p-5 space-y-4">
      <label className="block">
        <span className="text-xs font-semibold uppercase text-text-dim">Code</span>
        <input
          value={code}
          onChange={(e) => setTyped(e.target.value)}
          placeholder="XXXX-XXXX"
          autoCapitalize="characters"
          spellCheck={false}
          className="mt-1 w-full px-3 py-2 text-lg font-mono tracking-widest rounded-lg bg-background border border-border text-foreground placeholder:text-text-dim focus:border-gold/60 focus:outline-none"
        />
      </label>

      {waiting && (
        <div className="space-y-2">
          <p className="text-sm text-text-muted">
            Waiting to link: <span className="text-foreground">{waiting.client_name}</span>
          </p>
          <ul className="space-y-1.5">
            {waiting.scopes.map((scope) => (
              <li
                key={scope}
                className={`flex items-start gap-2 text-sm ${
                  scope === "mods:write" ? "text-foreground" : "text-text-muted"
                }`}
              >
                {scope === "mods:write" ? (
                  <Upload className="w-4 h-4 text-accent-red shrink-0 mt-0.5" />
                ) : (
                  <span aria-hidden className="text-text-dim shrink-0 mt-0.5">
                    •
                  </span>
                )}
                <span>{describeScope(scope)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex items-start gap-3 rounded-lg border border-accent-red/30 bg-accent-red/5 p-3">
        <ShieldAlert className="w-5 h-5 text-accent-red shrink-0 mt-0.5" />
        <p className="text-xs text-text-muted">
          Only approve a code{" "}
          <strong className="text-foreground">an app on your own machine</strong> is showing right
          now. If someone sent you this code or asked you to enter it, they are trying to{" "}
          {publishes ? "publish mods under your name" : "post as you"} — deny it.
          {publishes && (
            <>
              {" "}
              <strong className="text-foreground">
                This code asks to publish, which is the one worth being sure about:
              </strong>{" "}
              releases it uploads carry your name and your signature.
            </>
          )}
        </p>
      </div>

      {error && <p className="text-sm text-accent-red">{error}</p>}

      <div className="flex gap-2">
        <button
          onClick={() => decide(true)}
          disabled={busy || !waiting}
          className="flex-1 px-4 py-2 text-sm font-semibold rounded-lg bg-gold text-background disabled:opacity-40 cursor-pointer"
        >
          Approve
        </button>
        <button
          onClick={() => decide(false)}
          disabled={busy || code.length < 8}
          className="px-4 py-2 text-sm font-semibold rounded-lg border border-border text-text-muted hover:text-foreground disabled:opacity-40 cursor-pointer"
        >
          Deny
        </button>
      </div>

      <p className="text-[11px] text-text-dim">
        {waiting
          ? `Approving grants exactly what is listed above, for ${waiting.key_ttl_days} days.`
          : "Approving grants only what the waiting app asked for, and only for a few months."}{" "}
        You can revoke it from{" "}
        <Link href="/account/keys" className="text-gold hover:underline">
          your API keys
        </Link>{" "}
        at any time.
      </p>
    </div>
  );
}

export default function LinkDevicePage() {
  return (
    <>
      <Navbar />
      <main className="pt-32 md:pt-36 pb-16 px-6 max-w-xl mx-auto">
        <h1 className="flex items-center gap-3 text-3xl font-black text-foreground mb-2">
          <KeyRound className="w-7 h-7 text-gold" />
          Link a device
        </h1>
        <p className="text-text-muted text-sm mb-8">
          MJOLNIR desktop apps show a code when you sign in from the desktop — the launcher to rate
          and comment as you, the tag editor to publish your mods. Enter it here to say yes.
        </p>
        {/* useSearchParams opts its subtree out of prerendering; the boundary
            keeps that to the form. */}
        <Suspense fallback={<div className="h-64" />}>
          <LinkForm />
        </Suspense>
      </main>
      <Footer />
    </>
  );
}
