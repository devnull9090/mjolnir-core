"use client";

/**
 * Self-service API keys: create with scopes, see the key exactly once,
 * revoke. The listing shows prefixes only — the server stores hashes.
 */
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Copy, KeyRound, Plus, Trash2 } from "lucide-react";

import { Navbar } from "../../components/Navbar";
import { Footer } from "../../components/Footer";

const ALL_SCOPES = ["mods:read", "mods:write", "ratings:write", "comments:write"];

interface Key {
  id: string;
  name: string;
  key_prefix: string;
  scopes: string[];
  last_used_at: string | null;
  expires_at: string | null;
  created_at: string;
}

export default function ApiKeysPage() {
  const [signedIn, setSignedIn] = useState<boolean | null>(null);
  const [keys, setKeys] = useState<Key[]>([]);
  const [name, setName] = useState("");
  const [scopes, setScopes] = useState<string[]>(["mods:read"]);
  const [fresh, setFresh] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(
    () =>
      fetch("/api/v1/account/api-keys")
        .then((r) => {
          setSignedIn(r.ok);
          return r.ok ? r.json() : { keys: [] };
        })
        .then((d) => setKeys(d.keys)),
    [],
  );

  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    void load();
  }, [load]);
  /* eslint-enable react-hooks/set-state-in-effect */

  const create = async () => {
    setBusy(true);
    setError(null);
    const res = await fetch("/api/v1/account/api-keys", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, scopes }),
    });
    const body = await res.json().catch(() => ({}));
    if (res.ok) {
      setFresh(body.key);
      setName("");
      await load();
    } else {
      setError(body.message ?? body.error ?? "Failed");
    }
    setBusy(false);
  };

  const revoke = async (id: string) => {
    await fetch(`/api/v1/account/api-keys/${id}`, { method: "DELETE" });
    await load();
  };

  return (
    <>
      <Navbar />
      <main className="pt-32 md:pt-36 pb-16 px-6 max-w-2xl mx-auto">
        <h1 className="flex items-center gap-3 text-3xl font-black text-foreground mb-2">
          <KeyRound className="w-7 h-7 text-gold" />
          API keys
        </h1>
        <p className="text-text-muted text-sm mb-8">
          For mod managers and other tools integrating with{" "}
          <Link href="/docs/api" className="text-gold hover:underline">
            the open API
          </Link>
          . Keys are scoped, revocable, and shown exactly once.
        </p>

        {signedIn === false && (
          <div className="rounded-xl border border-border p-8 text-center">
            <p className="text-text-muted mb-4">Sign in to manage keys.</p>
            {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
            <a
              href="/api/v1/auth/discord?next=/account/keys"
              className="inline-block px-4 py-2 text-sm font-semibold rounded-lg bg-[#5865F2] text-white hover:brightness-110"
            >
              Sign in with Discord
            </a>
          </div>
        )}

        {signedIn && (
          <>
            {/* Create */}
            <div className="rounded-xl border border-border p-5 mb-8">
              <div className="flex gap-2 mb-3">
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Key name, e.g. my-mod-manager"
                  className="flex-1 px-3 py-2 text-sm rounded-lg bg-background border border-border text-foreground placeholder:text-text-dim focus:border-gold/60 focus:outline-none"
                />
                <button
                  onClick={create}
                  disabled={busy || !name.trim() || scopes.length === 0}
                  className="flex items-center gap-2 px-4 py-2 text-sm font-semibold rounded-lg bg-gold text-background disabled:opacity-40"
                >
                  <Plus className="w-4 h-4" />
                  Create
                </button>
              </div>
              <div className="flex flex-wrap gap-2">
                {ALL_SCOPES.map((s) => (
                  <label
                    key={s}
                    className={`px-2.5 py-1 rounded-lg border text-xs font-mono cursor-pointer transition-colors ${
                      scopes.includes(s)
                        ? "border-gold/60 text-gold"
                        : "border-border text-text-dim hover:text-foreground"
                    }`}
                  >
                    <input
                      type="checkbox"
                      className="hidden"
                      checked={scopes.includes(s)}
                      onChange={(e) =>
                        setScopes((p) => (e.target.checked ? [...p, s] : p.filter((x) => x !== s)))
                      }
                    />
                    {s}
                  </label>
                ))}
              </div>
              {error && <p className="mt-3 text-sm text-red-400">{error}</p>}
            </div>

            {/* Fresh key, shown once */}
            {fresh && (
              <div className="mb-8 rounded-xl border border-gold/40 bg-gold/5 p-4">
                <p className="text-sm text-foreground font-semibold mb-2">
                  Copy this key now — it will not be shown again.
                </p>
                <div className="flex items-center gap-2">
                  <code className="flex-1 px-3 py-2 text-xs font-mono rounded-lg bg-background border border-border text-gold break-all">
                    {fresh}
                  </code>
                  <button
                    onClick={() => navigator.clipboard.writeText(fresh)}
                    className="p-2 rounded-lg border border-border text-text-muted hover:text-foreground"
                    aria-label="Copy key"
                  >
                    <Copy className="w-4 h-4" />
                  </button>
                </div>
              </div>
            )}

            {/* Listing */}
            <div className="space-y-2">
              {keys.map((k) => (
                <div key={k.id} className="flex items-center gap-3 rounded-lg border border-border px-4 py-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold text-foreground">{k.name}</span>
                      <code className="text-[11px] font-mono text-text-dim">{k.key_prefix}…</code>
                    </div>
                    <div className="text-[11px] text-text-dim mt-0.5">
                      {k.scopes.join(" · ")}
                      {k.last_used_at ? ` · last used ${k.last_used_at.slice(0, 10)}` : " · never used"}
                    </div>
                  </div>
                  <button
                    onClick={() => revoke(k.id)}
                    className="text-text-dim hover:text-red-400"
                    aria-label={`Revoke ${k.name}`}
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))}
              {keys.length === 0 && <p className="text-sm text-text-dim">No keys yet.</p>}
            </div>
          </>
        )}
      </main>
      <Footer />
    </>
  );
}
