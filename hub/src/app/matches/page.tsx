import Link from "next/link";
import { getCloudflareContext } from "@opennextjs/cloudflare";

import { Navbar } from "../components/Navbar";
import { Footer } from "../components/Footer";
import { JoinButton } from "../components/JoinButton";
import { listLobbies } from "@/lib/api/lobby";
import { listMatches } from "@/lib/api/matches";
import { listMaps } from "@/lib/api/maps";
import { GAME_TYPE_NAMES } from "@/kit/types";
import { marketingMetadata } from "@/lib/marketing";
import { MatchTable } from "./_components/MatchTable";

export const metadata = marketingMetadata(
  "Halo Campaign Evolved Match History | MJOLNIR Core",
  "Every public Campaign Evolved multiplayer match on the classic Halo CE maps: who won, the scoreboard, and every kill.",
  "/matches",
);

// Live data: never cached.
export const dynamic = "force-dynamic";

const MODES = ["all", "slayer", "ctf", "team_slayer", "koth", "oddball"];

/** How many live games the strip above the history shows. */
const LIVE_SHOWN = 6;

function num(v: unknown): number | null {
  return v === undefined || v === null || v === "" ? null : Number(v);
}

export default async function MatchesPage({
  searchParams,
}: {
  searchParams: Promise<{ map?: string; mode?: string; before?: string; player?: string }>;
}) {
  const params = await searchParams;
  const mode = MODES.find((m) => m === params.mode) ?? "all";
  const map = /^[A-Z0-9]{3}$/.test(params.map ?? "") ? params.map : undefined;
  const before = /^[\d\- :]{10,19}$/.test(params.before ?? "") ? params.before : undefined;

  const { env, cf } = getCloudflareContext();
  const me = {
    latitude: num((cf as Record<string, unknown> | undefined)?.latitude),
    longitude: num((cf as Record<string, unknown> | undefined)?.longitude),
  };
  const [{ matches, next }, maps, lobbies] = await Promise.all([
    listMatches(env.DB as never, { map, game_type: mode === "all" ? undefined : mode, before }),
    listMaps(env.DB as never),
    listLobbies(env.DB as never, { has_space: true }, me),
  ]);
  const live = lobbies.slice(0, LIVE_SHOWN);

  const qs = (over: Record<string, string | undefined>) => {
    const merged = { map, mode, ...over };
    const u = new URLSearchParams();
    for (const [k, v] of Object.entries(merged)) if (v && v !== "all") u.set(k, v);
    const s = u.toString();
    return s ? `/matches?${s}` : "/matches";
  };
  const chip = (active: boolean) =>
    `px-3 py-1.5 rounded-full border transition-colors ${
      active ? "border-gold/60 text-gold bg-gold/10" : "border-border text-text-muted hover:text-foreground"
    }`;

  return (
    <>
      <Navbar />

      <main className="marketing pt-40 md:pt-44 pb-16 px-6 max-w-6xl mx-auto">
        <div className="mb-8">
          <h1 className="text-4xl font-black text-foreground mb-3">Match history</h1>
          <p className="text-text-muted text-lg max-w-2xl">
            Every public match, reported by its host when it ends: the scoreboard and every kill, with
            where it happened.
          </p>
          <div className="mt-4 flex flex-wrap items-center gap-4">
            <Link href="/games" className="text-sm font-semibold text-gold hover:underline">Live games →</Link>
            <form action="/players" className="flex items-center gap-2">
              <input
                name="name"
                placeholder="Find a player"
                maxLength={64}
                className="px-3 py-1.5 rounded-full border border-border bg-surface text-sm text-foreground placeholder:text-text-dim focus:outline-none focus:border-gold/60"
              />
            </form>
          </div>
        </div>

        {/* Games with room right now, nearest first: history is what
            happened, and this is where to go next. */}
        {live.length > 0 && (
          <section className="mb-10">
            <div className="mb-3 flex items-baseline justify-between gap-4">
              <h2 className="text-sm font-bold uppercase text-text-dim">Live now</h2>
              <Link href="/games" className="text-sm font-semibold text-gold hover:underline">
                All live games →
              </Link>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {live.map((l) => (
                <div
                  key={l.id}
                  className="flex items-center justify-between gap-3 rounded-xl border border-border bg-surface px-4 py-3"
                >
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-foreground truncate">{l.map_title ?? l.map_code}</p>
                    <p className="text-xs text-text-dim truncate">
                      {GAME_TYPE_NAMES[l.game_type] ?? l.game_type} · {l.players}/{l.max_players} players
                    </p>
                  </div>
                  <JoinButton lobbyId={l.id} />
                </div>
              ))}
            </div>
          </section>
        )}

        <div className="mb-3 flex flex-wrap items-center gap-1 text-xs">
          {MODES.map((m) => (
            <Link key={m} href={qs({ mode: m })} className={chip(m === mode)}>
              {m === "all" ? "All game types" : (GAME_TYPE_NAMES[m] ?? m)}
            </Link>
          ))}
        </div>
        <div className="mb-8 flex flex-wrap items-center gap-1 text-xs">
          <Link href={qs({ map: undefined })} className={chip(!map)}>
            All maps
          </Link>
          {maps.map((m) => (
            <Link key={m.code} href={qs({ map: m.code })} className={chip(map === m.code)}>
              {m.title}
            </Link>
          ))}
        </div>

        <MatchTable matches={matches} />

        {(before || next) && (
          <div className="mt-6 flex gap-4 text-sm">
            {before && (
              <Link href={qs({ before: undefined })} className="text-text-muted hover:text-foreground">
                ← Newest
              </Link>
            )}
            {next && (
              <Link href={qs({ before: next })} className="text-gold hover:underline">
                Older →
              </Link>
            )}
          </div>
        )}
      </main>

      <Footer />
    </>
  );
}
