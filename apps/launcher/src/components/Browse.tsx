import { useCallback, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";

/**
 * The Hub view: browse and install content mods from mjolnircore.com, keep
 * a per-profile load order with computed conflict badges, and install the
 * Ed25519-signed code-mod set.
 */

interface HubMod {
  id: string;
  slug: string;
  name: string;
  summary: string | null;
  category: string;
  author: string;
  download_count: number;
  rating_mean: number | null;
  rating_count: number;
}

interface InstalledMod {
  slug: string;
  name: string;
  release_id: string;
  version: string;
  containers: string[];
}

interface ProfileEntry {
  slug: string;
  enabled: boolean;
}

interface Profile {
  name: string;
  entries: ProfileEntry[];
}

interface HubState {
  installed: InstalledMod[];
  profiles: Profile[];
  active: string;
}

interface ConflictPair {
  a: string;
  b: string;
  shared_chunks: number;
}

interface CodeModRow {
  id: string;
  file: string;
  sha256: string;
  size: number;
  version: string;
  summary: string;
  category: string;
  installed_version: string | null;
  update_available: boolean;
}

interface CodeModsStatus {
  set_version: string;
  signature_verified: boolean;
  mods: CodeModRow[];
}

export default function Browse() {
  const [mods, setMods] = useState<HubMod[]>([]);
  const [state, setState] = useState<HubState | null>(null);
  const [conflicts, setConflicts] = useState<ConflictPair[]>([]);
  const [codeMods, setCodeMods] = useState<CodeModsStatus | null>(null);
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [hubDown, setHubDown] = useState(false);

  const refreshState = useCallback(async () => {
    const s = await invoke<HubState>("hub_state");
    setState(s);
    try {
      const c = await invoke<{ pairs: ConflictPair[] }>("hub_check_conflicts");
      setConflicts(c.pairs);
    } catch {
      // Conflicts need the network; the local state is still authoritative.
      setConflicts([]);
    }
  }, []);

  const refreshList = useCallback(async (q: string) => {
    try {
      const r = await invoke<{ mods: HubMod[] }>("hub_list_mods", {
        query: q || null,
      });
      setMods(r.mods);
      setHubDown(false);
    } catch {
      setHubDown(true);
    }
  }, []);

  useEffect(() => {
    void refreshState();
    void refreshList("");
    invoke<CodeModsStatus>("code_mods_status").then(setCodeMods).catch(() => {});
  }, [refreshState, refreshList]);

  const run = async (key: string, cmd: string, args?: Record<string, unknown>) => {
    setBusy(key);
    setError(null);
    try {
      const next = await invoke<HubState>(cmd, args);
      setState(next);
      await refreshState();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(null);
    }
  };

  const activeProfile = state?.profiles.find((p) => p.name === state.active);
  const installedSlugs = new Set(state?.installed.map((m) => m.slug));
  const releaseToSlug = new Map(state?.installed.map((m) => [m.release_id, m.slug]));
  const conflictsOf = (slug: string) =>
    conflicts
      .filter((p) => releaseToSlug.get(p.a) === slug || releaseToSlug.get(p.b) === slug)
      .map((p) => ({
        other: releaseToSlug.get(releaseToSlug.get(p.a) === slug ? p.b : p.a) ?? "?",
        chunks: p.shared_chunks,
      }));

  return (
    <div className="space-y-8">
      {error && (
        <div className="rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-2 text-sm text-red-300">
          {error}
        </div>
      )}

      {/* ── Load order ── */}
      <section>
        <div className="flex items-baseline justify-between mb-3">
          <div>
            <h2 className="text-xl font-bold">Installed content mods</h2>
            <p className="text-sm text-text-secondary mt-0.5">
              Later entries win when two mods edit the same game data.
            </p>
          </div>
          <ProfileBar state={state} busy={busy} run={run} />
        </div>

        {!activeProfile || activeProfile.entries.length === 0 ? (
          <p className="text-sm text-text-secondary border border-dashed border-border-subtle rounded-xl p-6 text-center">
            Nothing installed in this profile yet — pick something below.
          </p>
        ) : (
          <div className="space-y-1.5">
            {activeProfile.entries.map((entry, i) => {
              const inst = state!.installed.find((m) => m.slug === entry.slug);
              const rowConflicts = entry.enabled ? conflictsOf(entry.slug) : [];
              return (
                <div
                  key={entry.slug}
                  className={`bg-surface-secondary border border-border-subtle rounded-xl px-4 py-3 flex items-center gap-3 ${
                    entry.enabled ? "" : "opacity-50"
                  }`}
                >
                  <span className="text-xs font-mono text-text-secondary w-6">{i + 1}</span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold truncate">{inst?.name ?? entry.slug}</span>
                      <span className="text-[11px] px-1.5 py-0.5 rounded bg-surface-hover text-text-secondary">
                        v{inst?.version}
                      </span>
                      {rowConflicts.map((c) => (
                        <span
                          key={c.other}
                          title={`${c.chunks} shared chunk${c.chunks === 1 ? "" : "s"} with ${c.other}; the lower entry wins them`}
                          className="text-[11px] px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-400"
                        >
                          ⚡ {c.other}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="flex items-center gap-1 shrink-0">
                    <button
                      aria-label="Move up"
                      disabled={i === 0 || !!busy}
                      onClick={() => void run(entry.slug, "hub_set_order", { slug: entry.slug, index: i - 1 })}
                      className="px-2 py-1 rounded text-text-secondary hover:text-text-primary disabled:opacity-30 cursor-pointer"
                    >
                      ↑
                    </button>
                    <button
                      aria-label="Move down"
                      disabled={i === activeProfile.entries.length - 1 || !!busy}
                      onClick={() => void run(entry.slug, "hub_set_order", { slug: entry.slug, index: i + 1 })}
                      className="px-2 py-1 rounded text-text-secondary hover:text-text-primary disabled:opacity-30 cursor-pointer"
                    >
                      ↓
                    </button>
                    <button
                      onClick={() =>
                        void run(entry.slug, "hub_set_enabled", { slug: entry.slug, enabled: !entry.enabled })
                      }
                      disabled={!!busy}
                      className="px-2.5 py-1 rounded-lg text-xs border border-border-subtle text-text-secondary hover:text-text-primary cursor-pointer"
                    >
                      {entry.enabled ? "Disable" : "Enable"}
                    </button>
                    <button
                      onClick={() => void run(entry.slug, "hub_uninstall", { slug: entry.slug })}
                      disabled={!!busy}
                      className="px-2.5 py-1 rounded-lg text-xs border border-red-500/30 text-red-400 hover:bg-red-500/10 cursor-pointer"
                    >
                      Remove
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* ── Browse hub ── */}
      <section>
        <div className="flex items-center justify-between mb-3 gap-3">
          <div>
            <h2 className="text-xl font-bold">Browse the Hub</h2>
            <p className="text-sm text-text-secondary mt-0.5">
              Community content mods from mjolnircore.com — data only, scanned at upload.
            </p>
          </div>
          <input
            type="search"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              void refreshList(e.target.value);
            }}
            placeholder="Search…"
            className="px-3 py-1.5 text-sm rounded-lg bg-surface-secondary border border-border-subtle focus:border-mjolnir-gold/60 focus:outline-none w-52"
          />
        </div>

        {hubDown ? (
          <p className="text-sm text-amber-400/80">
            Could not reach the hub. Installed mods keep working offline.
          </p>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            {mods.map((mod) => (
              <div
                key={mod.id}
                className="bg-surface-secondary border border-border-subtle rounded-xl p-4 flex items-start gap-3"
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold truncate">{mod.name}</span>
                    <span className="text-[11px] px-1.5 py-0.5 rounded bg-surface-hover text-text-secondary uppercase">
                      {mod.category}
                    </span>
                  </div>
                  <p className="text-sm text-text-secondary mt-1 line-clamp-2">{mod.summary}</p>
                  <p className="text-xs text-text-secondary mt-1">
                    by {mod.author} · {mod.download_count} downloads
                    {mod.rating_mean !== null && ` · ★ ${mod.rating_mean.toFixed(1)} (${mod.rating_count})`}
                  </p>
                </div>
                <button
                  onClick={() => void run(mod.slug, "hub_install", { slug: mod.slug })}
                  disabled={!!busy || installedSlugs.has(mod.slug)}
                  className="shrink-0 px-3 py-2 rounded-lg text-sm font-medium border border-mjolnir-gold/40 text-mjolnir-gold hover:bg-mjolnir-gold/10 disabled:opacity-40 cursor-pointer transition-all"
                >
                  {installedSlugs.has(mod.slug)
                    ? "Installed"
                    : busy === mod.slug
                      ? "Installing…"
                      : "Install"}
                </button>
              </div>
            ))}
            {mods.length === 0 && (
              <p className="text-sm text-text-secondary">No published mods match.</p>
            )}
          </div>
        )}
      </section>

      {/* ── Signed code mods ── */}
      <section>
        <div className="mb-3">
          <h2 className="text-xl font-bold flex items-center gap-2">
            Code mods
            {codeMods &&
              (codeMods.signature_verified ? (
                <span className="text-[11px] px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-400">
                  ✓ signature verified · set v{codeMods.set_version}
                </span>
              ) : (
                <span className="text-[11px] px-1.5 py-0.5 rounded bg-red-500/15 text-red-400">
                  ✗ SIGNATURE FAILED — installs disabled
                </span>
              ))}
          </h2>
          <p className="text-sm text-text-secondary mt-0.5">
            UE4SS script mods, reviewed in mjolnir-core and shipped as an Ed25519-signed set.
            This launcher verifies the signature before installing anything.
          </p>
        </div>

        {!codeMods ? (
          <p className="text-sm text-text-secondary">No signed set published yet.</p>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            {codeMods.mods.map((m) => {
              const installed = m.installed_version !== null;
              return (
                <div
                  key={m.id}
                  className="bg-surface-secondary border border-border-subtle rounded-xl px-4 py-3 flex items-center gap-3"
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold">{m.id}</span>
                      <span className="text-[11px] px-1.5 py-0.5 rounded bg-surface-hover text-text-secondary">
                        v{m.version}
                      </span>
                      {m.update_available && (
                        <span className="text-[11px] px-1.5 py-0.5 rounded bg-mjolnir-gold/15 text-mjolnir-gold">
                          update
                        </span>
                      )}
                    </div>
                    {m.summary && (
                      <p className="text-xs text-text-secondary mt-0.5 line-clamp-1">{m.summary}</p>
                    )}
                    <p className="text-xs text-text-secondary font-mono truncate" title={m.sha256}>
                      sha256 {m.sha256.slice(0, 16)}…
                    </p>
                  </div>
                  <button
                    onClick={async () => {
                      setBusy(m.id);
                      setError(null);
                      try {
                        await invoke("code_mods_install", { id: m.id });
                        const s = await invoke<CodeModsStatus>("code_mods_status");
                        setCodeMods(s);
                      } catch (e) {
                        setError(String(e));
                      } finally {
                        setBusy(null);
                      }
                    }}
                    disabled={!!busy || (installed && !m.update_available) || !codeMods.signature_verified}
                    className="shrink-0 px-3 py-1.5 rounded-lg text-xs font-medium border border-mjolnir-gold/40 text-mjolnir-gold hover:bg-mjolnir-gold/10 disabled:opacity-40 cursor-pointer"
                  >
                    {busy === m.id
                      ? "Installing…"
                      : m.update_available
                        ? "Update"
                        : installed
                          ? "Installed"
                          : "Install"}
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}

function ProfileBar({
  state,
  busy,
  run,
}: {
  state: HubState | null;
  busy: string | null;
  run: (key: string, cmd: string, args?: Record<string, unknown>) => Promise<void>;
}) {
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");

  if (!state) return null;
  return (
    <div className="flex items-center gap-2">
      <select
        value={state.active}
        onChange={(e) => void run("profile", "hub_profile_switch", { name: e.target.value })}
        disabled={!!busy}
        className="px-2 py-1.5 text-sm rounded-lg bg-surface-secondary border border-border-subtle cursor-pointer"
        aria-label="Profile"
      >
        {state.profiles.map((p) => (
          <option key={p.name} value={p.name}>
            {p.name}
          </option>
        ))}
      </select>
      {creating ? (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (name.trim()) {
              void run("profile", "hub_profile_create", { name: name.trim(), copyActive: true });
              setCreating(false);
              setName("");
            }
          }}
          className="flex items-center gap-1"
        >
          <input
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            onBlur={() => setCreating(false)}
            placeholder="Profile name"
            className="px-2 py-1.5 text-sm rounded-lg bg-surface-secondary border border-border-subtle w-32 focus:outline-none focus:border-mjolnir-gold/60"
          />
        </form>
      ) : (
        <button
          onClick={() => setCreating(true)}
          className="px-2 py-1.5 text-sm rounded-lg border border-border-subtle text-text-secondary hover:text-text-primary cursor-pointer"
          title="New profile (copies the current one)"
        >
          +
        </button>
      )}
      {state.profiles.length > 1 && (
        <button
          onClick={() => void run("profile", "hub_profile_delete", { name: state.active })}
          disabled={!!busy}
          className="px-2 py-1.5 text-sm rounded-lg border border-border-subtle text-text-secondary hover:text-red-400 cursor-pointer"
          title="Delete this profile"
        >
          ×
        </button>
      )}
    </div>
  );
}
