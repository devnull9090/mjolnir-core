"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

import { Navbar } from "../../components/Navbar";
import { Footer } from "../../components/Footer";

const CATEGORIES = ["gameplay", "maps", "textures", "weapons", "camera", "tools", "framework", "multiplayer"];

export default function NewModPage() {
  const router = useRouter();
  const [signedIn, setSignedIn] = useState<boolean | null>(null);
  const [slug, setSlug] = useState("");
  const [name, setName] = useState("");
  const [summary, setSummary] = useState("");
  const [category, setCategory] = useState("gameplay");
  const [license, setLicense] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    fetch("/api/v1/auth/me").then((r) => setSignedIn(r.ok));
  }, []);

  const create = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const res = await fetch("/api/v1/mods", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        slug,
        name,
        summary: summary || undefined,
        category,
        license: license || undefined,
      }),
    });
    if (res.ok) {
      router.push(`/mods/${slug}/manage`);
      return;
    }
    const body = await res.json().catch(() => ({}));
    setError(body.message ?? body.error ?? `Failed (${res.status})`);
    setBusy(false);
  };

  return (
    <>
      <Navbar />
      <main className="pt-32 md:pt-36 pb-16 px-6 max-w-xl mx-auto">
        <h1 className="text-3xl font-black text-foreground mb-2">Publish a mod</h1>
        <p className="text-text-muted mb-8 text-sm">
          Content mods only — tags, textures, maps, sounds. Anything that runs code (Lua, DLLs)
          ships through{" "}
          <Link href="https://github.com/devnull9090/mjolnir-core" className="text-gold hover:underline">
            mjolnir-core
          </Link>{" "}
          pull requests instead, where it is reviewed and signed.
        </p>

        {signedIn === false && (
          <div className="rounded-xl border border-border p-8 text-center">
            <p className="text-text-muted mb-4">Sign in to publish.</p>
            {/* Full-page navigation on purpose: this is the OAuth entry, not a page. */}
            {/* eslint-disable-next-line @next/next/no-html-link-for-pages */}
            <a
              href="/api/v1/auth/discord?next=/mods/new"
              className="inline-block px-4 py-2 text-sm font-semibold rounded-lg bg-[#5865F2] text-white hover:brightness-110"
            >
              Sign in with Discord
            </a>
          </div>
        )}

        {signedIn && (
          <form onSubmit={create} className="space-y-5">
            <div>
              <label htmlFor="name" className="block text-sm font-semibold text-foreground mb-1">
                Name
              </label>
              <input
                id="name"
                required
                value={name}
                onChange={(e) => {
                  setName(e.target.value);
                  if (!slug || slug === toSlug(name)) setSlug(toSlug(e.target.value));
                }}
                className="w-full px-3 py-2 text-sm rounded-lg bg-background border border-border text-foreground focus:border-gold/60 focus:outline-none"
                placeholder="My Texture Pack"
              />
            </div>
            <div>
              <label htmlFor="slug" className="block text-sm font-semibold text-foreground mb-1">
                Slug
              </label>
              <input
                id="slug"
                required
                pattern="[a-z0-9][a-z0-9-]{1,63}"
                value={slug}
                onChange={(e) => setSlug(e.target.value)}
                className="w-full px-3 py-2 text-sm font-mono rounded-lg bg-background border border-border text-foreground focus:border-gold/60 focus:outline-none"
                placeholder="my-texture-pack"
              />
              <p className="text-[11px] text-text-dim mt-1">mjolnircore.com/mods/{slug || "…"}</p>
            </div>
            <div>
              <label htmlFor="summary" className="block text-sm font-semibold text-foreground mb-1">
                Summary
              </label>
              <input
                id="summary"
                maxLength={300}
                value={summary}
                onChange={(e) => setSummary(e.target.value)}
                className="w-full px-3 py-2 text-sm rounded-lg bg-background border border-border text-foreground focus:border-gold/60 focus:outline-none"
                placeholder="One line shown on the mod card"
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label htmlFor="category" className="block text-sm font-semibold text-foreground mb-1">
                  Category
                </label>
                <select
                  id="category"
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  className="w-full px-3 py-2 text-sm rounded-lg bg-background border border-border text-foreground focus:border-gold/60 focus:outline-none capitalize"
                >
                  {CATEGORIES.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor="license" className="block text-sm font-semibold text-foreground mb-1">
                  License <span className="text-text-dim font-normal">(optional)</span>
                </label>
                <input
                  id="license"
                  value={license}
                  onChange={(e) => setLicense(e.target.value)}
                  className="w-full px-3 py-2 text-sm rounded-lg bg-background border border-border text-foreground focus:border-gold/60 focus:outline-none"
                  placeholder="MIT, CC-BY-4.0, …"
                />
              </div>
            </div>

            {error && <p className="text-sm text-red-400">{error}</p>}

            <button
              type="submit"
              disabled={busy}
              className="px-5 py-2.5 text-sm font-semibold rounded-lg bg-gold text-background hover:brightness-110 disabled:opacity-40 transition-all"
            >
              {busy ? "Creating…" : "Create draft"}
            </button>
            <p className="text-[11px] text-text-dim">
              The mod stays private until its first release passes the automated scan.
            </p>
          </form>
        )}
      </main>
      <Footer />
    </>
  );
}

function toSlug(s: string): string {
  return s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 64);
}
