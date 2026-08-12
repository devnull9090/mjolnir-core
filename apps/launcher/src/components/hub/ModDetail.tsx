/**
 * A mod's page, inside the launcher.
 *
 * Deliberately the same page the website shows — screenshots, description,
 * releases, ratings and reviews, comments — because the decision to install
 * something is made on that information, and making people leave the
 * launcher to find it is how you end up with a launcher nobody browses in.
 * Every one of those blocks is the shared component the website renders.
 */
import { useEffect, useState } from "react";
import {
  ActionButton,
  Avatar,
  Badge,
  CommentThread,
  ErrorNote,
  ModGallery,
  RatingPanel,
  ReleaseChangesPanel,
  ReleaseList,
  ReportButton,
  Spinner,
  TypeBadge,
  UserLink,
  formatCount,
  timeAgo,
  useHub,
  type ModDetail as ModDetailType,
  type Release,
} from "@mjolnir/hub-kit";

import { conflictsFor, type Library } from "../../hub/library";
import { HUB_SITE } from "../../hub/client";

export function ModDetail({
  slug,
  library,
  onBack,
}: {
  slug: string;
  library: Library;
  onBack: () => void;
}) {
  const { client, openUrl } = useHub();
  const [mod, setMod] = useState<ModDetailType | null>(null);
  const [releases, setReleases] = useState<Release[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setMod(null);
    setError(null);
    Promise.all([client.getMod(slug), client.listReleases(slug)])
      .then(([m, r]) => {
        if (!live) return;
        setMod(m);
        setReleases(r);
      })
      .catch((e) => live && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      live = false;
    };
  }, [client, slug]);

  const installed = library.state?.installed.find((m) => m.slug === slug);
  const update = library.updates.find((u) => u.slug === slug);
  const verified = library.verified[slug];
  const entry = library.state?.profiles
    .find((p) => p.name === library.state?.active)
    ?.entries.find((e) => e.slug === slug);
  const conflicts = conflictsFor(slug, library.state, library.conflicts);
  const busy = library.busy === slug;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <ActionButton tone="neutral" size="sm" onClick={onBack}>
          ← Back
        </ActionButton>
        <button
          onClick={() => openUrl(`${HUB_SITE}/mods/${slug}`)}
          className="text-xs text-text-secondary hover:text-text-primary cursor-pointer"
        >
          Open on mjolnircore.com ↗
        </button>
      </div>

      {error && <ErrorNote>{error}</ErrorNote>}
      {library.error && <ErrorNote>{library.error}</ErrorNote>}

      {!mod ? (
        <p className="flex items-center gap-2 text-sm text-text-secondary">
          <Spinner /> Loading…
        </p>
      ) : (
        <>
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <h2 className="text-2xl font-bold">{mod.name}</h2>
                <TypeBadge type={mod.type} />
                <Badge>{mod.category}</Badge>
                {installed && <Badge tone="green">v{installed.version} installed</Badge>}
                {verified && !verified.ok && (
                  <Badge tone="red" title={[...verified.tampered, ...verified.missing].join(", ")}>
                    files changed since install
                  </Badge>
                )}
              </div>
              <p className="flex flex-wrap items-center gap-x-1.5 text-sm text-text-secondary mt-1">
                <span>by</span>
                <Avatar url={mod.author_avatar} size="xs" />
                <UserLink userId={mod.owner_id} name={mod.author} className="text-text-primary" />
                <span>
                  {mod.license ? `· ${mod.license} ` : ""}· {formatCount(mod.download_count)}{" "}
                  downloads · updated {timeAgo(mod.updated_at)}
                </span>
              </p>
            </div>

            {mod.type === "content" && (
              <div className="flex items-center gap-2">
                {installed ? (
                  <>
                    {update && (
                      <ActionButton
                        disabled={!!library.busy}
                        onClick={() =>
                          void library.run(slug, "hub_install", {
                            slug,
                            releaseId: update.latest_release_id,
                          })
                        }
                      >
                        {busy ? "Updating…" : `Update to ${update.latest_version}`}
                      </ActionButton>
                    )}
                    <ActionButton
                      tone="neutral"
                      disabled={!!library.busy || !entry}
                      onClick={() =>
                        void library.run(slug, "hub_set_enabled", {
                          slug,
                          enabled: !entry?.enabled,
                        })
                      }
                    >
                      {entry?.enabled ? "Disable" : "Enable"}
                    </ActionButton>
                    <ActionButton
                      tone="danger"
                      disabled={!!library.busy}
                      onClick={() => void library.run(slug, "hub_uninstall", { slug })}
                    >
                      Remove
                    </ActionButton>
                  </>
                ) : (
                  <ActionButton
                    disabled={!!library.busy}
                    onClick={() => void library.run(slug, "hub_install", { slug })}
                  >
                    {busy ? "Installing…" : "Install"}
                  </ActionButton>
                )}
              </div>
            )}
          </div>

          {mod.type !== "content" && (
            <p className="text-sm text-text-secondary rounded-lg border border-accent-blue/30 bg-accent-blue/5 px-4 py-3">
              This mod executes code, so it ships only in the Ed25519-signed set the launcher
              verifies. Install it from the <strong>Code mods</strong> tab.
            </p>
          )}

          {conflicts.length > 0 && (
            <p className="text-sm text-amber-400/90 rounded-lg border border-amber-500/30 bg-amber-500/5 px-4 py-3">
              Shares game data with {conflicts.map((c) => `${c.other} (${c.chunks})`).join(", ")}.
              Whichever sits lower in the load order wins those chunks — not an error, just
              something to order deliberately.
            </p>
          )}

          <ModGallery slug={slug} />

          <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_320px] gap-8">
            <div className="space-y-8 min-w-0">
              {mod.summary && <p className="text-text-secondary">{mod.summary}</p>}
              {mod.description_md ? (
                <article className="text-sm text-text-secondary whitespace-pre-wrap break-words">
                  {mod.description_md}
                </article>
              ) : (
                <p className="text-sm text-text-secondary">No description yet.</p>
              )}

              {/* What the latest release actually edits — the declared
                  change list, shown before anyone decides to install. */}
              {mod.type === "content" && releases[0] && (
                <div>
                  <h3 className="text-sm font-bold uppercase text-text-secondary mb-3">
                    What this mod does
                  </h3>
                  <ReleaseChangesPanel releaseId={releases[0].id} />
                </div>
              )}

              <CommentThread slug={slug} />
            </div>

            <aside className="space-y-6">
              <div>
                <h3 className="text-sm font-bold uppercase text-text-secondary mb-3">Releases</h3>
                <ReleaseList
                  releases={releases}
                  highlight={installed?.version ?? null}
                  action={(r) =>
                    mod.type === "content" && installed?.release_id !== r.id ? (
                      <ActionButton
                        size="sm"
                        tone="neutral"
                        disabled={!!library.busy}
                        title={`Install v${r.version}`}
                        onClick={() =>
                          void library.run(slug, "hub_install", { slug, releaseId: r.id })
                        }
                      >
                        Install
                      </ActionButton>
                    ) : null
                  }
                />
              </div>

              <div>
                <h3 className="text-sm font-bold uppercase text-text-secondary mb-3">
                  Ratings &amp; reviews
                </h3>
                <RatingPanel slug={slug} />
              </div>

              <ReportButton subjectId={mod.id} label="Report this mod" />
            </aside>
          </div>
        </>
      )}
    </div>
  );
}
