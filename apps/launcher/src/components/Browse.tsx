/**
 * Browse Hub — finding things, not managing them.
 *
 * This view used to also own the installed list and the load order, which
 * put "your mods" in two places at once. Installed things now live under My
 * Mods; what is left here is discovery: the community catalogue and the
 * signed code-mod set, each with an Install button and a full mod page.
 *
 * Everything the catalogue renders — cards, galleries, ratings, reviews,
 * comments, release lists — is the same component the website renders
 * (hub/src/kit). This file is the launcher's shell around it.
 */
import { useState } from "react";
import { ActionButton, useHub } from "@mjolnir/hub-kit";

import { HUB_SITE } from "../hub/client";
import type { Library } from "../hub/library";
import { ModBrowser } from "./hub/ModBrowser";
import { CodeModsPanel } from "./hub/CodeModsPanel";

type Tab = "content" | "code";

export default function Browse({
  library,
  onOpenMod,
}: {
  library: Library;
  onOpenMod: (slug: string) => void;
}) {
  const [tab, setTab] = useState<Tab>("content");

  const tabs: { key: Tab; label: string; hint: string }[] = [
    { key: "content", label: "Content mods", hint: "Community game data — maps, textures, tuning" },
    { key: "code", label: "Code mods", hint: "Signed UE4SS scripts from mjolnir-core" },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold">Browse the Hub</h2>
          <p className="text-sm text-text-secondary mt-0.5">
            Everything published on mjolnircore.com. Installed mods are managed under My Mods.
          </p>
        </div>
        <AccountChip />
      </div>

      <div className="flex items-center gap-1">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            title={t.hint}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors cursor-pointer ${
              tab === t.key
                ? "bg-surface-card text-text-primary"
                : "text-text-secondary hover:text-text-primary"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "content" ? (
        <ModBrowser library={library} onSelect={onOpenMod} />
      ) : (
        <CodeModsPanel />
      )}
    </div>
  );
}

/** Who the launcher is posting as, and how to change that. */
export function AccountChip() {
  const { user, ready, signIn, signOut, openUrl } = useHub();

  if (!ready) return <div className="w-24 h-8" />;

  if (!user) {
    return (
      <ActionButton size="sm" onClick={signIn} title="Needed to rate or comment">
        Sign in to the Hub
      </ActionButton>
    );
  }

  return (
    <div className="flex items-center gap-2">
      {user.avatar_url && <img src={user.avatar_url} alt="" className="w-6 h-6 rounded-full" />}
      <span className="text-sm max-w-32 truncate">{user.display_name ?? user.username}</span>
      <button
        onClick={() => openUrl(`${HUB_SITE}/account/keys`)}
        title="Manage or revoke this launcher's access"
        className="text-xs text-text-secondary hover:text-text-primary cursor-pointer"
      >
        keys ↗
      </button>
      <button
        onClick={signOut}
        title="Forget this account on this machine"
        className="text-xs text-text-secondary hover:text-accent-red cursor-pointer"
      >
        Sign out
      </button>
    </div>
  );
}
