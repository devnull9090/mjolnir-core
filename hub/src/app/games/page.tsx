import Link from "next/link";
import { Users } from "lucide-react";
import { getCloudflareContext } from "@opennextjs/cloudflare";

import { Navbar } from "../components/Navbar";
import { Footer } from "../components/Footer";
import { listLobbies } from "@/lib/api/lobby";
import { listMaps } from "@/lib/api/maps";
import { GAME_TYPE_NAMES } from "@/kit/types";
import { marketingMetadata } from "@/lib/marketing";

export const metadata = marketingMetadata(
  "Halo Campaign Evolved Multiplayer Games | MJOLNIR Core",
  "Find reported Campaign Evolved multiplayer lobbies on classic Halo CE maps. Get MJOLNIR, install the maps, and connect with the community.",
  "/games",
);

// Live data: never cached.
export const dynamic = "force-dynamic";

const MODES = ["all", "slayer", "ctf", "team_slayer", "koth", "oddball"];

function num(v: unknown): number | null {
  return v === undefined || v === null || v === "" ? null : Number(v);
}

export default async function GamesPage({
  searchParams,
}: {
  searchParams: Promise<{ map?: string; mode?: string; open?: string }>;
}) {
  const params = await searchParams;
  const mode = MODES.find((m) => m === params.mode) ?? "all";
  const map = /^[A-Z0-9]{3}$/.test(params.map ?? "") ? params.map : undefined;
  const open = params.open === "1";

  const { env, cf } = getCloudflareContext();
  const me = {
    latitude: num((cf as Record<string, unknown> | undefined)?.latitude),
    longitude: num((cf as Record<string, unknown> | undefined)?.longitude),
  };
  const [lobbies, maps] = await Promise.all([
    listLobbies(
      env.DB as never,
      { map, game_type: mode === "all" ? undefined : mode, has_space: open },
      me,
    ),
    listMaps(env.DB as never),
  ]);

  const qs = (over: Record<string, string | undefined>) => {
    const merged = { map, mode, open: open ? "1" : undefined, ...over };
    const u = new URLSearchParams();
    for (const [k, v] of Object.entries(merged)) if (v && v !== "all") u.set(k, v);
    const s = u.toString();
    return s ? `/games?${s}` : "/games";
  };

  return (
    <>
      <Navbar />

      <main className="marketing pt-40 md:pt-44 pb-16 px-6 max-w-6xl mx-auto">
        <div className="mb-8">
          <h1 className="text-4xl font-black text-foreground mb-3">Campaign Evolved multiplayer games</h1>
          <p className="text-text-muted text-lg max-w-2xl">
            Multiplayer games on the classic maps, live now. Join from the game: MULTIPLAYER, then
            FIND GAMES. Ping is an estimate from where you and the host are.
          </p>
          <Link href="/multiplayer" className="mt-4 inline-block text-sm font-semibold text-gold hover:underline">Get multiplayer &amp; find your fireteam →</Link>
        </div>

        <div className="mb-3 flex flex-wrap items-center gap-1 text-xs">
          {MODES.map((m) => (
            <Link
              key={m}
              href={qs({ mode: m })}
              className={`px-3 py-1.5 rounded-full border transition-colors ${
                m === mode
                  ? "border-gold/60 text-gold bg-gold/10"
                  : "border-border text-text-muted hover:text-foreground"
              }`}
            >
              {m === "all" ? "All game types" : (GAME_TYPE_NAMES[m] ?? m)}
            </Link>
          ))}
          <Link
            href={qs({ open: open ? undefined : "1" })}
            className={`ml-2 px-3 py-1.5 rounded-full border transition-colors ${
              open ? "border-gold/60 text-gold bg-gold/10" : "border-border text-text-muted hover:text-foreground"
            }`}
          >
            Has room
          </Link>
        </div>
        <div className="mb-8 flex flex-wrap items-center gap-1 text-xs">
          <Link
            href={qs({ map: undefined })}
            className={`px-3 py-1.5 rounded-full border transition-colors ${
              !map ? "border-gold/60 text-gold bg-gold/10" : "border-border text-text-muted hover:text-foreground"
            }`}
          >
            All maps
          </Link>
          {maps.map((m) => (
            <Link
              key={m.code}
              href={qs({ map: m.code })}
              className={`px-3 py-1.5 rounded-full border transition-colors ${
                map === m.code
                  ? "border-gold/60 text-gold bg-gold/10"
                  : "border-border text-text-muted hover:text-foreground"
              }`}
            >
              {m.title}
            </Link>
          ))}
        </div>

        {lobbies.length === 0 ? (
          <div className="flex items-center gap-3 text-text-muted">
            <Users className="w-5 h-5" />
            <p>No games right now. Host one from the game and it shows up here.</p>
          </div>
        ) : (
          <div className="overflow-x-auto rounded-xl border border-border">
            <table className="w-full text-sm">
              <thead className="bg-surface-raised text-text-dim text-xs uppercase tracking-wide">
                <tr>
                  <th className="text-left px-4 py-3">Game</th>
                  <th className="text-left px-4 py-3">Map</th>
                  <th className="text-left px-4 py-3">Game type</th>
                  <th className="text-right px-4 py-3">Players</th>
                  <th className="text-right px-4 py-3">Ping</th>
                  <th className="text-left px-4 py-3">Host</th>
                </tr>
              </thead>
              <tbody>
                {lobbies.map((l) => (
                  <tr key={l.id} className="border-t border-border">
                    <td className="px-4 py-3 text-foreground font-medium">
                      {l.name}
                      {l.state === "in_game" && (
                        <span className="ml-2 text-[11px] text-text-dim">in game</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-text-muted">{l.map_title ?? l.map_code}</td>
                    <td className="px-4 py-3 text-text-muted">{GAME_TYPE_NAMES[l.game_type] ?? l.game_type}</td>
                    <td className="px-4 py-3 text-right text-foreground">
                      {l.players}/{l.max_players}
                    </td>
                    <td className="px-4 py-3 text-right text-text-muted">
                      {l.ping_ms === null ? "?" : `~${l.ping_ms} ms`}
                    </td>
                    <td className="px-4 py-3 text-text-muted">{l.host}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>

      <Footer />
    </>
  );
}
