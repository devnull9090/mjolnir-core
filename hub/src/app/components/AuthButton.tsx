"use client";

import { useEffect, useState } from "react";
import { LogOut } from "lucide-react";

interface Me {
  id: string;
  username: string;
  display_name: string | null;
  avatar_url: string | null;
}

/** Discord sign-in / signed-in chip for the navbar. */
export function AuthButton() {
  const [me, setMe] = useState<Me | null | undefined>(undefined); // undefined = loading

  useEffect(() => {
    fetch("/api/v1/auth/me")
      .then((r) => (r.ok ? r.json() : null))
      .then(setMe)
      .catch(() => setMe(null));
  }, []);

  if (me === undefined) return <div className="w-24" />;

  if (!me) {
    return (
      <a
        href={`/api/v1/auth/discord?next=${encodeURIComponent(
          typeof window !== "undefined" ? window.location.pathname : "/",
        )}`}
        className="px-3 py-1.5 text-sm font-semibold rounded-lg border border-[#5865F2]/60 text-[#8b95f6] hover:bg-[#5865F2]/10 transition-colors"
      >
        Sign in
      </a>
    );
  }

  return (
    <div className="flex items-center gap-2">
      {me.avatar_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={me.avatar_url} alt="" className="w-7 h-7 rounded-full" />
      ) : null}
      <span className="text-sm text-foreground font-medium max-w-28 truncate">
        {me.display_name ?? me.username}
      </span>
      <button
        title="Sign out"
        aria-label="Sign out"
        onClick={async () => {
          await fetch("/api/v1/auth/logout", { method: "POST" });
          setMe(null);
          window.location.reload();
        }}
        className="text-text-muted hover:text-foreground"
      >
        <LogOut className="w-4 h-4" />
      </button>
    </div>
  );
}
