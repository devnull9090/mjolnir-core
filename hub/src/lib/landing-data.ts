/**
 * Live hub telemetry for the landing pages (/, /multiplayer).
 *
 * Queries D1 directly in one parallel fan-out — the same worker, no HTTP hop —
 * and degrades cleanly to empty arrays / baseline figures if D1 is unreachable
 * or empty during local preview.
 */
import { getCloudflareContext } from "@opennextjs/cloudflare";
import type { D1Database } from "@cloudflare/workers-types";
import type { MapListing, Mod } from "@mjolnir/hub-kit/types";

import { getPosts, type BlogPost } from "./blog";
import { listLobbies, type Lobby } from "./api/lobby";
import { listMaps } from "./api/maps";
import { listMatches, type MatchSummary } from "./api/matches";
import { listPublishedMods } from "./api/queries";
import { leaderboard, podiumSpokes, type Standing } from "./api/leaderboards";
import type { RecordMatch } from "./api/player-record";

export interface HubTotals {
  maps: number;
  mods: number;
  matches: number;
  kills: number;
  downloads: number;
}

export interface LandingData {
  lobbies: Lobby[];
  livePlayers: number;
  recentMatches: MatchSummary[];
  latestMods: Mod[];
  maps: MapListing[];
  coversByCode: Map<string, string | null>;
  topPlayers: Standing[];
  topRings: Record<string, Pick<RecordMatch, "id" | "kills" | "deaths" | "outcome">[]>;
  totals: HubTotals;
  latestPost: BlogPost | null;
}

const EMPTY_TOTALS: HubTotals = {
  maps: 0,
  mods: 0,
  matches: 0,
  kills: 0,
  downloads: 0,
};

function num(v: unknown): number | null {
  return v === undefined || v === null || v === "" ? null : Number(v);
}

async function queryTotals(db: D1Database): Promise<HubTotals> {
  const row = await db
    .prepare(
      `SELECT
        (SELECT COUNT(*) FROM map_listings ml JOIN mods m ON m.id = ml.mod_id WHERE m.status = 'published') AS maps,
        (SELECT COUNT(*) FROM mods m WHERE m.status = 'published'
          AND NOT EXISTS (SELECT 1 FROM map_listings ml WHERE ml.mod_id = m.id)) AS mods,
        (SELECT COUNT(*) FROM matches m WHERE m.player_count >= 2
          AND EXISTS (SELECT 1 FROM match_players rp WHERE rp.match_id = m.id AND (rp.score <> 0 OR rp.kills > 0))) AS matches,
        (SELECT COALESCE(SUM(kills), 0) FROM match_players) AS kills,
        (SELECT COALESCE(SUM(download_count), 0) FROM mods WHERE status = 'published') AS downloads`,
    )
    .first<Record<string, unknown>>();
  const n = (v: unknown) => (typeof v === "number" ? v : Number(v) || 0);
  if (!row) return EMPTY_TOTALS;
  return {
    maps: n(row.maps),
    mods: n(row.mods),
    matches: n(row.matches),
    kills: n(row.kills),
    downloads: n(row.downloads),
  };
}

export async function getLandingData(): Promise<LandingData> {
  const latestPost = getPosts()[0] ?? null;
  const fallback: LandingData = {
    lobbies: [],
    livePlayers: 0,
    recentMatches: [],
    latestMods: [],
    maps: [],
    coversByCode: new Map(),
    topPlayers: [],
    topRings: {},
    totals: EMPTY_TOTALS,
    latestPost,
  };

  try {
    const { env, cf } = getCloudflareContext();
    const db = env.DB as unknown as D1Database | undefined;
    if (!db) return fallback;

    const me = {
      latitude: num((cf as Record<string, unknown> | undefined)?.latitude),
      longitude: num((cf as Record<string, unknown> | undefined)?.longitude),
    };

    const [lobbiesRes, matchesRes, modsRes, mapsRes, boardRes, totalsRes] = await Promise.allSettled([
      listLobbies(db as never, {}, me),
      listMatches(db as never, { real: true, limit: 3 }),
      listPublishedMods(db, { map: false, sort: "newest", limit: 4 }),
      listMaps(db as never),
      leaderboard(db as never, "kills", "all"),
      queryTotals(db),
    ]);

    const lobbies = lobbiesRes.status === "fulfilled" ? lobbiesRes.value : [];
    const recentMatches = matchesRes.status === "fulfilled" ? matchesRes.value.matches : [];
    const latestMods = modsRes.status === "fulfilled" ? modsRes.value : [];
    const maps = mapsRes.status === "fulfilled" ? mapsRes.value : [];
    const topPlayers = boardRes.status === "fulfilled" ? boardRes.value.standings.slice(0, 3) : [];
    const totals = totalsRes.status === "fulfilled" ? totalsRes.value : EMPTY_TOTALS;

    let topRings: LandingData["topRings"] = {};
    if (topPlayers.length > 0) {
      try {
        topRings = await podiumSpokes(
          db as never,
          topPlayers.map((p) => p.user.id),
        );
      } catch {
        topRings = {};
      }
    }

    const coversByCode = new Map(maps.map((m) => [m.code, m.cover_url]));
    const livePlayers = lobbies.reduce((sum, l) => sum + l.players, 0);

    return {
      lobbies,
      livePlayers,
      recentMatches,
      latestMods,
      maps,
      coversByCode,
      topPlayers,
      topRings,
      totals,
      latestPost,
    };
  } catch {
    return fallback;
  }
}
