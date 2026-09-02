/**
 * Someone's profile, inside the launcher.
 *
 * The same reasoning as ModDetail: the launcher renders the hub's community
 * surfaces rather than sending people to a browser for them, and an author's
 * name is one of the places browsing naturally goes. The head and the
 * figures are the shared <ProfileSummary> the website renders, so the two
 * cannot come to disagree about what an account's numbers are.
 *
 * The mods grid is local because a card means something different here: it
 * opens the launcher's own detail pane, with an Install button, rather than
 * a web page.
 */
import { useEffect, useState } from "react";
import {
  ActionButton,
  ErrorNote,
  ModCard,
  ProfileSummary,
  Spinner,
  useHub,
  type UserProfile as UserProfileType,
} from "@mjolnir/hub-kit";

import { HUB_SITE } from "../../hub/client";

export function UserProfile({
  userId,
  onBack,
  onOpenMod,
}: {
  userId: string;
  onBack: () => void;
  onOpenMod: (slug: string) => void;
}) {
  const { client, openUrl } = useHub();
  const [profile, setProfile] = useState<UserProfileType | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    setProfile(null);
    setError(null);
    client
      .getUserProfile(userId)
      .then((p) => live && setProfile(p))
      .catch((e) => live && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      live = false;
    };
  }, [client, userId]);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <ActionButton tone="neutral" size="sm" onClick={onBack}>
          ← Back
        </ActionButton>
        <button
          onClick={() => openUrl(`${HUB_SITE}/users/${userId}`)}
          className="text-xs text-text-secondary hover:text-text-primary cursor-pointer"
        >
          Open on mjolnircore.com ↗
        </button>
      </div>

      {error && <ErrorNote>{error}</ErrorNote>}

      {!profile ? (
        !error && (
          <p className="flex items-center gap-2 text-sm text-text-secondary">
            <Spinner /> Loading…
          </p>
        )
      ) : (
        <>
          <ProfileSummary profile={profile} />

          <section>
            <h3 className="text-sm font-bold uppercase text-text-secondary mb-3">
              Mods{profile.mods.length > 0 ? ` · ${profile.mods.length}` : ""}
            </h3>
            {profile.mods.length === 0 ? (
              <p className="text-sm text-text-secondary rounded-lg border border-border-subtle px-4 py-3">
                Nothing published yet.
              </p>
            ) : (
              <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                {profile.mods.map((mod) => (
                  <ModCard key={mod.id} mod={mod} onSelect={() => onOpenMod(mod.slug)} />
                ))}
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}
