/**
 * Wraps the hub views in the shared provider and owns signing in.
 *
 * Signing in from a desktop app means pairing, not a password box: the
 * launcher asks the hub for a code, opens mjolnircore.com/link in the real
 * browser where the user already has a Discord session, and waits. The key
 * that comes back is stored by the Rust side and never enters this webview.
 */
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { invoke } from "@tauri-apps/api/core";
import { openUrl } from "@tauri-apps/plugin-opener";
import { ActionButton, ErrorNote, HubProvider, Spinner, useHub } from "@mjolnir/hub-kit";

import { hubClient } from "./client";

interface Pairing {
  user_code: string;
  verification_url: string;
  interval: number;
  expires_in: number;
}

export function HubShell({
  children,
  onOpenProfile,
}: {
  children: ReactNode;
  /** Shows a user's profile in-app; the kit links author names through it. */
  onOpenProfile: (userId: string) => void;
}) {
  const [pairing, setPairing] = useState<Pairing | null>(null);
  const [open, setOpen] = useState(false);

  return (
    <HubProvider
      client={hubClient}
      onSignIn={() => setOpen(true)}
      onSignOut={() => invoke("hub_sign_out")}
      onOpenUrl={(url) => {
        void openUrl(url);
      }}
      // Not `profileHref`: the launcher's views are component state, and an
      // anchor would navigate the whole webview off the app.
      openProfile={onOpenProfile}
    >
      {children}
      {open && (
        <PairingDialog
          pairing={pairing}
          setPairing={setPairing}
          onClose={() => {
            setOpen(false);
            setPairing(null);
          }}
        />
      )}
    </HubProvider>
  );
}

function PairingDialog({
  pairing,
  setPairing,
  onClose,
}: {
  pairing: Pairing | null;
  setPairing: (p: Pairing | null) => void;
  onClose: () => void;
}) {
  const { refreshUser } = useHub();
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<"starting" | "waiting" | "done">("starting");
  const started = useRef(false);

  const start = useCallback(async () => {
    setError(null);
    setStatus("starting");
    try {
      const p = await invoke<Pairing>("hub_auth_start");
      setPairing(p);
      setStatus("waiting");
      await openUrl(p.verification_url);
    } catch (e) {
      setError(String(e));
      setStatus("starting");
    }
  }, [setPairing]);

  useEffect(() => {
    // React runs effects twice in development; one handshake is enough.
    if (started.current) return;
    started.current = true;
    void start();
  }, [start]);

  // Poll for the approval. The hub tells us how often it wants to be asked.
  useEffect(() => {
    if (status !== "waiting" || !pairing) return;
    let live = true;
    const timer = setInterval(
      async () => {
        try {
          const res = await invoke<{ status: string }>("hub_auth_poll");
          if (!live) return;
          if (res.status === "approved") {
            setStatus("done");
            refreshUser();
            setTimeout(onClose, 1200);
          } else if (res.status === "denied") {
            setError("The request was denied on the website.");
            setStatus("starting");
          } else if (res.status === "expired") {
            setError("That code expired. Start again for a fresh one.");
            setStatus("starting");
          }
        } catch (e) {
          if (live) setError(String(e));
        }
      },
      Math.max(2, pairing.interval) * 1000,
    );
    return () => {
      live = false;
      clearInterval(timer);
    };
  }, [status, pairing, refreshUser, onClose]);

  return (
    <div
      className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-6"
      role="dialog"
      aria-modal="true"
      aria-label="Sign in to the hub"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-xl border border-border-subtle bg-surface-secondary p-6 space-y-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div>
          <h2 className="text-lg font-bold">Sign in to the Hub</h2>
          <p className="text-sm text-text-secondary mt-1">
            Rating and commenting need a hub account. Your browser opens at
            mjolnircore.com/link — approve the code below there, signed in with Discord.
          </p>
        </div>

        {error && <ErrorNote>{error}</ErrorNote>}

        {status === "done" ? (
          <p className="text-sm text-accent-green">Linked. Welcome back.</p>
        ) : pairing ? (
          <>
            <div className="rounded-lg border border-mjolnir-gold/40 bg-mjolnir-gold/5 py-4 text-center">
              <p className="text-xs uppercase tracking-wide text-text-secondary mb-1">Your code</p>
              <p className="text-3xl font-mono tracking-[0.3em] text-mjolnir-gold select-text">
                {pairing.user_code}
              </p>
            </div>
            <p className="flex items-center gap-2 text-xs text-text-secondary">
              <Spinner className="w-3 h-3" />
              Waiting for approval…
            </p>
            <div className="flex gap-2">
              <ActionButton
                tone="neutral"
                size="sm"
                onClick={() => void openUrl(pairing.verification_url)}
              >
                Open the page again
              </ActionButton>
              <ActionButton tone="neutral" size="sm" onClick={onClose}>
                Cancel
              </ActionButton>
            </div>
          </>
        ) : (
          <div className="flex items-center gap-2 text-sm text-text-secondary">
            <Spinner />
            Asking the hub for a code…
            <ActionButton tone="neutral" size="sm" onClick={() => void start()}>
              Retry
            </ActionButton>
          </div>
        )}

        <p className="text-[11px] text-text-secondary">
          The launcher receives a key limited to reading, rating and commenting — it cannot
          publish mods. Revoke it any time under Account → API keys on the website.
        </p>
      </div>
    </div>
  );
}
