/**
 * What is installed from the hub, in the order it mounts.
 *
 * Load order is the whole point of this panel: later entries win the game
 * data they share with earlier ones, so the list is draggable-by-arrows and
 * says which pairs actually overlap. Updates and integrity live here too —
 * both are statements about this machine, not about the catalogue.
 */
import {
  ActionButton,
  Badge,
  BoltIcon,
  ErrorNote,
  RefreshIcon,
  ShieldIcon,
  timeAgo,
} from "@mjolnir/hub-kit";
import { useState } from "react";

import { conflictsFor, type Library } from "../../hub/library";

export function InstalledPanel({
  library,
  onSelect,
  onGoToUpdates,
}: {
  library: Library;
  onSelect: (slug: string) => void;
  /** Bulk updating lives in the update manager; this is how rows get there. */
  onGoToUpdates?: () => void;
}) {
  const { state, updates, verified, busy } = library;
  const profile = state?.profiles.find((p) => p.name === state.active);
  const entries = profile?.entries ?? [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h3 className="text-lg font-bold">Content mods</h3>
          <p className="text-sm text-text-secondary mt-0.5">
            Game data from the hub. Later entries win when two mods edit the same thing.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <ActionButton
            tone="neutral"
            size="sm"
            onClick={() => void library.checkUpdates()}
            disabled={!!busy}
            title="Ask the hub what is newer"
          >
            <RefreshIcon className="w-3.5 h-3.5" />
            Re-check
          </ActionButton>
          <ProfileBar library={library} />
        </div>
      </div>

      {updates.length > 0 && onGoToUpdates && (
        <button
          onClick={onGoToUpdates}
          className="w-full text-left text-sm rounded-lg border border-mjolnir-gold/30 bg-mjolnir-gold/5 px-4 py-2.5 text-mjolnir-gold hover:bg-mjolnir-gold/10 cursor-pointer"
        >
          {updates.length} content mod{updates.length === 1 ? " has" : "s have"} a newer version —
          open the update manager to pick what to update →
        </button>
      )}

      {library.error && <ErrorNote>{library.error}</ErrorNote>}

      {entries.length === 0 ? (
        <p className="text-sm text-text-secondary border border-dashed border-border-subtle rounded-xl p-6 text-center">
          No content mods in this profile yet — find some on the Browse Hub tab.
        </p>
      ) : (
        <div className="space-y-1.5">
          {entries.map((entry, i) => {
            const inst = state?.installed.find((m) => m.slug === entry.slug);
            const update = updates.find((u) => u.slug === entry.slug);
            const check = verified[entry.slug];
            const rowConflicts = entry.enabled
              ? conflictsFor(entry.slug, state, library.conflicts)
              : [];
            return (
              <div
                key={entry.slug}
                // Wraps rather than squeezes: at the launcher's default
                // window width the controls would otherwise crush the name
                // down to a few characters.
                className={`bg-surface-secondary border border-border-subtle rounded-xl px-4 py-3 flex flex-wrap items-center gap-x-3 gap-y-2 ${
                  entry.enabled ? "" : "opacity-50"
                }`}
              >
                <span className="text-xs font-mono text-text-secondary w-6">{i + 1}</span>
                <button
                  onClick={() => onSelect(entry.slug)}
                  className="flex-1 min-w-56 text-left cursor-pointer"
                >
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-semibold truncate">{inst?.name ?? entry.slug}</span>
                    <Badge>v{inst?.version ?? "?"}</Badge>
                    {update && (
                      <Badge tone="gold" title={update.changelog ?? undefined}>
                        v{update.latest_version} available
                      </Badge>
                    )}
                    {inst?.signature_verified && (
                      <Badge tone="green" title="Release signature verified against the pinned key">
                        <ShieldIcon className="w-3 h-3" />
                        signed
                      </Badge>
                    )}
                    {inst?.signer_fingerprint && (
                      <Badge
                        tone="green"
                        title={`Author-signed: the archive contents verified against key ${inst.signer_fingerprint.slice(0, 16)}… at install.`}
                      >
                        <ShieldIcon className="w-3 h-3" />
                        author
                      </Badge>
                    )}
                    {inst?.signature_notice && (
                      <Badge tone="amber" title={inst.signature_notice}>
                        key notice
                      </Badge>
                    )}
                    {check && !check.ok && (
                      <Badge
                        tone="red"
                        title={`Changed or missing since install: ${[
                          ...check.tampered,
                          ...check.missing,
                        ].join(", ")}`}
                      >
                        integrity
                      </Badge>
                    )}
                    {rowConflicts.map((c) => (
                      <Badge
                        key={c.other}
                        tone="amber"
                        title={`${c.chunks} shared chunk${
                          c.chunks === 1 ? "" : "s"
                        } with ${c.other}; the lower entry wins them`}
                      >
                        <BoltIcon className="w-3 h-3" />
                        {c.other}
                      </Badge>
                    ))}
                  </div>
                  {inst?.installed_at && (
                    <p className="text-[11px] text-text-secondary mt-0.5">
                      installed {timeAgo(new Date(inst.installed_at * 1000).toISOString())}
                    </p>
                  )}
                </button>

                <div className="flex items-center gap-1 shrink-0 ml-auto">
                  {update && (
                    <ActionButton
                      size="sm"
                      disabled={!!busy}
                      onClick={() =>
                        void library.run(entry.slug, "hub_install", {
                          slug: entry.slug,
                          releaseId: update.latest_release_id,
                        })
                      }
                    >
                      {busy === entry.slug ? "Updating…" : "Update"}
                    </ActionButton>
                  )}
                  <button
                    aria-label={`Move ${entry.slug} up`}
                    disabled={i === 0 || !!busy}
                    onClick={() =>
                      void library.run(entry.slug, "hub_set_order", {
                        slug: entry.slug,
                        index: i - 1,
                      })
                    }
                    className="px-2 py-1 rounded text-text-secondary hover:text-text-primary disabled:opacity-30 cursor-pointer"
                  >
                    ↑
                  </button>
                  <button
                    aria-label={`Move ${entry.slug} down`}
                    disabled={i === entries.length - 1 || !!busy}
                    onClick={() =>
                      void library.run(entry.slug, "hub_set_order", {
                        slug: entry.slug,
                        index: i + 1,
                      })
                    }
                    className="px-2 py-1 rounded text-text-secondary hover:text-text-primary disabled:opacity-30 cursor-pointer"
                  >
                    ↓
                  </button>
                  <ActionButton
                    size="sm"
                    tone="neutral"
                    disabled={!!busy}
                    onClick={() =>
                      void library.run(entry.slug, "hub_set_enabled", {
                        slug: entry.slug,
                        enabled: !entry.enabled,
                      })
                    }
                  >
                    {entry.enabled ? "Disable" : "Enable"}
                  </ActionButton>
                  <ActionButton
                    size="sm"
                    tone="danger"
                    disabled={!!busy}
                    onClick={() => void library.run(entry.slug, "hub_uninstall", { slug: entry.slug })}
                  >
                    Remove
                  </ActionButton>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function ProfileBar({ library }: { library: Library }) {
  const { state, busy, run } = library;
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
          className="px-2 py-1.5 text-sm rounded-lg border border-border-subtle text-text-secondary hover:text-accent-red cursor-pointer"
          title="Delete this profile"
        >
          ×
        </button>
      )}
    </div>
  );
}
