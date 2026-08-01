"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Settings } from "lucide-react";

/** Shows the Manage link to the mod's owner (or a moderator). */
export function OwnerBar({ slug, ownerId }: { slug: string; ownerId: string }) {
  const [canManage, setCanManage] = useState(false);

  useEffect(() => {
    fetch("/api/v1/auth/me")
      .then((r) => (r.ok ? r.json() : null))
      .then((me) => {
        if (me && (me.id === ownerId || me.role !== "user")) setCanManage(true);
      })
      .catch(() => {});
  }, [ownerId]);

  if (!canManage) return null;
  return (
    <Link
      href={`/mods/${slug}/manage`}
      className="flex items-center gap-2 px-4 py-2 text-sm font-semibold rounded-lg border border-border text-text-muted hover:text-foreground hover:border-gold/40 transition-all"
    >
      <Settings className="w-4 h-4" />
      Manage
    </Link>
  );
}
